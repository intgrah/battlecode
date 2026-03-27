"""Connect Ax excess to the nearest Ti conveyor with flow.

Finds Ax harvesters with excess and builds a chain of conveyors from the
harvester to the nearest Ti conveyor carrying Ti flow. This creates mixed
Ti+Ax flow at the junction, which triggers the place_foundry task.

Uses the Ax chain A* with Ti and RAx leakage banned to ensure the Ax chain
stays pure.
"""

from ax_chain_astar import AxChainAstar
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
from flow_astar import RAX, TI
from marker import MarkerTaskClaim, TaskKind

from .build import Action, PlaceBridge, PlaceConveyor
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road
from .state import State


def connect_excess_ax_ti_conv(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    best_tile: Position | None = None
    best_dist = 999999
    w = state.w
    f = state.my_flow
    for p in state.my_harvesters | state.my_transport:
        i = state.idx(p.x, p.y)
        if f.ax_excess[i] > 0.01 and not is_claimed(state, i, TaskKind.FIX_EXCESS):
            dist = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_tile = p
    if best_tile is None:
        return None

    ti_goals = _find_ti_conveyor_goals(state)
    if not ti_goals:
        return None

    ti_idx = state.idx(best_tile.x, best_tile.y)
    rnd = ct.get_current_round()
    state.claim = MarkerTaskClaim(TaskKind.FIX_EXCESS, ti_idx, rnd)
    state.debug_target = (best_tile, 255, 0, 255)

    sx, sy = best_tile.x, best_tile.y
    si = state.idx(sx, sy)
    bld = state.building[si]
    match bld:
        case BuildingHarvester() | BuildingFoundry():
            banned = TI | RAX
            start = None
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
                    state.leakage_mask is not None
                    and state.leakage_mask[ni] & banned != 0
                ):
                    continue
                start = Position(nx, ny)
                break
            if start is None:
                return None
            sx, sy = start.x, start.y

    start = Position(sx, sy)
    path = state.ax_cached_path
    if path is None or state.ax_cached_source != start:
        if state.ax_flow_search is None or state.ax_cached_source != start:
            state.ax_flow_search = AxChainAstar(
                state,
                sx,
                sy,
                ti_goals,
            )
            state.ax_cached_source = start
        path = state.ax_flow_search.compute(lambda: ct.get_cpu_time_elapsed() < 1200)
        if state.ax_flow_search.exhausted:
            state.ax_flow_search = None
        state.ax_cached_path = path
    if path is None or len(path) < 2:
        state.ax_cached_path = None
        return None

    for k in range(len(path) - 1):
        x, y = path[k] % w, path[k] // w
        nx, ny = path[k + 1] % w, path[k + 1] // w

        pi = path[k]
        pbld = state.building[pi]
        if (
            pbld is not None
            and pbld.team == state.my_team
            and isinstance(
                pbld,
                (
                    BuildingConveyor,
                    BuildingArmouredConveyor,
                    BuildingSplitter,
                    BuildingBridge,
                    BuildingCore,
                ),
            )
        ):
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


def _find_ti_conveyor_goals(state: State) -> set[int]:
    f = state.my_flow
    goals: set[int] = set()
    for p in state.my_transport:
        i = state.idx(p.x, p.y)
        if f.ti[i] <= 0:
            continue
        bld = state.building[i]
        match bld:
            case BuildingConveyor() | BuildingArmouredConveyor():
                goals.add(i)
    return goals
