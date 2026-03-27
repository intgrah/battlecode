"""Connect Ti or RAx excess to the core.

Finds tiles with Ti or RAx excess (flow produced but not reaching the core)
and builds a conveyor/bridge chain from the excess tile to the core. Uses
the flow A* with Ax leakage banned to prevent mixing.
"""

from building import (
    ArmouredConveyor,
    Bridge,
    Conveyor,
    Core,
    Foundry,
    Harvester,
    Splitter,
)
from cambc import Controller, Direction, Environment, Position
from flow_astar import AX, FlowAstar
from marker import TaskClaim, TaskKind

from .build import Action, PlaceBridge, PlaceConveyor
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road
from .state import State


def connect_excess_ti_rax_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    w = state.w
    best_tile: Position | None = None
    best_dist = 999999
    f = state.my_flow
    for p in state.my_harvesters | state.my_transport | state.my_foundries:
        i = state.idx(p.x, p.y)
        ti_ex = f.ti_excess[i]
        rax_ex = f.rax_excess[i]
        if (ti_ex > 0.01 or rax_ex > 0.01) and not is_claimed(
            state,
            i,
            TaskKind.FIX_EXCESS,
        ):
            dist = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_tile = p
    if best_tile is None:
        return None

    idx = state.idx(best_tile.x, best_tile.y)
    rnd = ct.get_current_round()
    state.claim = TaskClaim(TaskKind.FIX_EXCESS, idx, rnd)
    state.debug_target = (best_tile, 255, 0, 0)

    sx, sy = best_tile.x, best_tile.y
    si = state.idx(sx, sy)
    bld = state.building[si]

    if bld is not None:
        match bld:
            case Harvester() | Foundry():
                cx, cy = state.my_core
                start: Position | None = None
                best_d = 999999
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
                    nbld = state.building[ni]
                    if isinstance(nbld, (Conveyor, ArmouredConveyor, Splitter, Bridge)):
                        continue
                    d = (nx - cx) ** 2 + (ny - cy) ** 2
                    if d < best_d:
                        best_d = d
                        start = Position(nx, ny)
                if start is None:
                    return None
                sx, sy = start
            case (
                Conveyor(direction=d)
                | ArmouredConveyor(direction=d)
                | Splitter(direction=d)
            ):
                ddx, ddy = d.delta()
                ox, oy = sx + ddx, sy + ddy
                if state.in_bounds(ox, oy):
                    sx, sy = ox, oy
            case Bridge(target=bt):
                sx, sy = bt

    start = Position(sx, sy)
    path = state.ti_cached_path
    if path is None or state.ti_cached_source != start:
        if state.ti_flow_search is None or state.ti_cached_source != start:
            core_goals = {state.idx(p.x, p.y) for p in state.my_core_tiles}
            state.ti_flow_search = FlowAstar(
                state,
                sx,
                sy,
                core_goals,
                AX,
            )
            state.ti_cached_source = start
        state.ti_flow_search.set_budget(ct, 1200)
        state.ti_flow_search.compute()
        path = state.ti_flow_search.get_path()
        if state.ti_flow_search.done:
            state.ti_flow_search = None
        state.ti_cached_path = path
    if path is None or len(path) < 2:
        state.ti_cached_path = None
        return None

    for k in range(len(path) - 1):
        x, y = path[k] % w, path[k] // w
        nx, ny = path[k + 1] % w, path[k + 1] // w

        pi = path[k]
        pbld = state.building[pi]
        if pbld is not None and pbld.team == state.my_team:
            match pbld:
                case Core():
                    continue
                case (
                    Conveyor(direction=td)
                    | ArmouredConveyor(direction=td)
                    | Splitter(direction=td)
                ):
                    ddx, ddy = td.delta()
                    if (x + ddx, y + ddy) == (nx, ny):
                        continue
                case Bridge(target=bt) if bt == (nx, ny):
                    continue

        build_at = Position(x, y)
        dx, dy = nx - x, ny - y
        is_cardinal = abs(dx) + abs(dy) == 1

        if pos == build_at:
            adj = cardinal_adjacent(state, pos, build_at)
            if adj is not None:
                return move_toward_with_road(state, ct, adj)
            continue

        if is_cardinal:
            if pos.distance_squared(build_at) <= 2:
                d = build_at.direction_to(Position(nx, ny))
                return Direction.CENTRE, PlaceConveyor(build_at, d)
            adj = cardinal_adjacent(state, pos, build_at)
            if adj is not None:
                return move_toward_with_road(state, ct, adj)
            continue

        if pos.distance_squared(build_at) <= 2:
            return Direction.CENTRE, PlaceBridge(build_at, Position(nx, ny))
        adj = cardinal_adjacent(state, pos, build_at)
        if adj is not None:
            return move_toward_with_road(state, ct, adj)

    return None
