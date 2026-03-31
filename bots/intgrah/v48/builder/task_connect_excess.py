from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from ax_chain_astar import AxChainAstar
from bridge_astar import BridgeFlowAstar
from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingHarvester,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from flow_astar import AX, RAX, TI, FlowAstar
from marker import MarkerTaskClaim, TaskKind
from splitter_bridge_astar import SplitterBridgeAstar
from util import INF

from .build import Action, PlaceBridge, PlaceConveyor
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road

if TYPE_CHECKING:
    from algorithms import Astar

    from .state import State


class ExcessKind(Enum):
    TI_RAX = auto()
    AX = auto()


class SearchKind(Enum):
    MIXED = auto()
    BRIDGE = auto()
    AX_CHAIN = auto()
    SPLITTER = auto()


def connect_excess(
    state: State,
    ct: Controller,
    excess_kind: ExcessKind,
    search_kind: SearchKind,
) -> tuple[Direction, Action | None] | None:
    best_tile = _find_excess_tile(state, excess_kind)
    if best_tile is None:
        return None

    goals = _make_goals(state, search_kind)
    if not goals:
        return None

    idx = state.idx(best_tile.x, best_tile.y)
    rnd = ct.get_current_round()
    state.claim = MarkerTaskClaim(TaskKind.FIX_EXCESS, idx, rnd)
    state.debug_target = (best_tile, 255, 128, 0)

    sx, sy = _step_off_source(state, best_tile, search_kind)
    if sx < 0:
        return None

    start = Position(sx, sy)
    path = _get_or_compute_path(state, ct, start, goals, search_kind)
    print(
        f"  excess={best_tile} start={start} goals={goals} path={path[:5] if path else None} kind={search_kind}",
    )
    if path is None or len(path) < 2:
        return None

    return _walk_path(state, ct, path, search_kind)


def _find_excess_tile(state: State, kind: ExcessKind) -> Position | None:
    pos = state.pos
    best: Position | None = None
    best_dist = INF
    f = state.my_flow
    match kind:
        case ExcessKind.TI_RAX:
            sources = state.my_harvesters | state.my_transport | state.my_foundries
        case ExcessKind.AX:
            sources = state.my_harvesters | state.my_transport
    for p in sources:
        i = state.idx(p.x, p.y)
        match kind:
            case ExcessKind.TI_RAX:
                has_excess = f.ti_excess[i] > 0.01 or f.rax_excess[i] > 0.01
            case ExcessKind.AX:
                has_excess = f.ax_excess[i] > 0.01
        if has_excess and not is_claimed(state, i, TaskKind.FIX_EXCESS):
            dist = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
            if dist < best_dist:
                best_dist = dist
                best = p
    return best


def _econ_goal_tiles(state: State) -> set[Position]:
    return state.my_econ_targets or state.my_core_tiles


def _make_goals(state: State, kind: SearchKind) -> set[int]:
    match kind:
        case SearchKind.MIXED | SearchKind.BRIDGE:
            return {state.idx(p.x, p.y) for p in _econ_goal_tiles(state)}
        case SearchKind.AX_CHAIN:
            return _find_ti_conveyor_goals(state)
        case SearchKind.SPLITTER:
            return {state.idx(p.x, p.y) for p in state.my_econ_targets}


def _find_ti_conveyor_goals(state: State) -> set[int]:
    f = state.my_flow
    goals: set[int] = set()
    for p in state.my_transport:
        i = state.idx(p.x, p.y)
        if f.ti[i] > 0:
            match state.building[i]:
                case BuildingConveyor() | BuildingArmouredConveyor():
                    goals.add(i)
    return goals


def _step_off_source(
    state: State,
    tile: Position,
    search_kind: SearchKind,
) -> tuple[int, int]:
    sx, sy = tile.x, tile.y
    si = state.idx(sx, sy)
    bld = state.building[si]
    if bld is None:
        return sx, sy

    match bld:
        case BuildingHarvester() | BuildingFoundry():
            return _find_adjacent_empty(state, sx, sy, search_kind)
        case BuildingBridge(target=bt):
            return bt.x, bt.y
        case (
            BuildingConveyor(direction=d)
            | BuildingArmouredConveyor(direction=d)
            | BuildingSplitter(direction=d)
        ) if search_kind == SearchKind.MIXED:
            ddx, ddy = d.delta()
            ox, oy = sx + ddx, sy + ddy
            if state.in_bounds(ox, oy):
                return ox, oy
    return sx, sy


def _find_adjacent_empty(
    state: State,
    sx: int,
    sy: int,
    search_kind: SearchKind,
) -> tuple[int, int]:
    banned = TI | RAX if search_kind == SearchKind.AX_CHAIN else 0
    best_pos = (-1, -1)
    best_d = INF
    for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = sx + ddx, sy + ddy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        env = state.env[ni]
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            continue
        match state.building[ni]:
            case (
                BuildingConveyor()
                | BuildingArmouredConveyor()
                | BuildingSplitter()
                | BuildingBridge()
            ):
                continue
        if (
            banned
            and state.leakage_mask is not None
            and state.leakage_mask[ni] & banned != 0
        ):
            continue
        d = (nx - state.my_core.x) ** 2 + (ny - state.my_core.y) ** 2
        if d < best_d:
            best_d = d
            best_pos = (nx, ny)
    return best_pos


def _get_or_compute_path(
    state: State,
    ct: Controller,
    start: Position,
    goals: set[int],
    kind: SearchKind,
) -> list[int] | None:
    cached_path, cached_source, search, set_cache = _cache_accessors(state, kind)

    if cached_path is not None and cached_source == start:
        return cached_path

    if search is None or cached_source != start:
        search = _make_search(state, start.x, start.y, goals, kind)
        set_cache(start, search, None)

    path = search.compute(lambda: ct.get_cpu_time_elapsed() < 1200)
    print(
        f"    search exhausted={search.exhausted} path={path[:5] if path else None} heap_size={len(search._heap)}",
    )
    if search.exhausted:
        search = None
    set_cache(start, search, path)

    if path is None or len(path) < 2:
        set_cache(start, search, None)
        return None
    return path


def _cache_accessors(
    state: State,
    kind: SearchKind,
) -> tuple[
    list[int] | None,
    Position | None,
    Astar[int] | None,
    object,
]:
    match kind:
        case SearchKind.MIXED:

            def _set(src: Position, s: Astar[int] | None, p: list[int] | None) -> None:
                state.ti_cached_source = src
                state.ti_flow_search = s
                state.ti_cached_path = p

            return (
                state.ti_cached_path,
                state.ti_cached_source,
                state.ti_flow_search,
                _set,
            )
        case SearchKind.BRIDGE | SearchKind.SPLITTER:

            def _set(src: Position, s: Astar[int] | None, p: list[int] | None) -> None:
                state.bridge_cached_source = src
                state.bridge_flow_search = s
                state.bridge_cached_path = p

            return (
                state.bridge_cached_path,
                state.bridge_cached_source,
                state.bridge_flow_search,
                _set,
            )
        case SearchKind.AX_CHAIN:

            def _set(src: Position, s: Astar[int] | None, p: list[int] | None) -> None:
                state.ax_cached_source = src
                state.ax_flow_search = s
                state.ax_cached_path = p

            return (
                state.ax_cached_path,
                state.ax_cached_source,
                state.ax_flow_search,
                _set,
            )


def _make_search(
    state: State,
    sx: int,
    sy: int,
    goals: set[int],
    kind: SearchKind,
) -> Astar[int]:
    match kind:
        case SearchKind.MIXED:
            return FlowAstar(state, sx, sy, goals, AX)
        case SearchKind.BRIDGE:
            return BridgeFlowAstar(state, sx, sy, goals, AX)
        case SearchKind.SPLITTER:
            return SplitterBridgeAstar(state, sx, sy, 0)
        case SearchKind.AX_CHAIN:
            return AxChainAstar(state, sx, sy, goals)


def _walk_path(
    state: State,
    ct: Controller,
    path: list[int],
    kind: SearchKind,
) -> tuple[Direction, Action | None] | None:
    w = state.w
    pos = state.pos
    for k in range(len(path) - 1):
        x, y = path[k] % w, path[k] // w
        nx, ny = path[k + 1] % w, path[k + 1] // w

        if _already_connected(state, path[k], x, y, nx, ny, kind):
            continue

        build_at = Position(x, y)

        if pos == build_at:
            adj = cardinal_adjacent(state, pos, build_at)
            if adj is not None:
                return move_toward_with_road(state, ct, adj)
            continue

        action = _build_action(build_at, nx, ny, kind)
        if pos.distance_squared(build_at) <= 2:
            return Direction.CENTRE, action
        adj = cardinal_adjacent(state, pos, build_at)
        if adj is not None:
            return move_toward_with_road(state, ct, adj)

    return None


def _already_connected(
    state: State,
    pi: int,
    x: int,
    y: int,
    nx: int,
    ny: int,
    kind: SearchKind,
) -> bool:
    pbld = state.building[pi]
    if pbld is None or pbld.team != state.my_team:
        return False
    match pbld:
        case BuildingCore():
            return True
        case BuildingBridge(target=bt) if bt.x == nx and bt.y == ny:
            return True
    if kind != SearchKind.BRIDGE:
        match pbld:
            case (
                BuildingConveyor(direction=td)
                | BuildingArmouredConveyor(direction=td)
                | BuildingSplitter(direction=td)
            ):
                ddx, ddy = td.delta()
                if (x + ddx, y + ddy) == (nx, ny):
                    return True
    return False


def _build_action(build_at: Position, nx: int, ny: int, kind: SearchKind) -> Action:
    target = Position(nx, ny)
    if kind != SearchKind.BRIDGE:
        dx, dy = nx - build_at.x, ny - build_at.y
        if abs(dx) + abs(dy) == 1:
            return PlaceConveyor(build_at, build_at.direction_to(target))
    return PlaceBridge(build_at, target)
