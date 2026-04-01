"""Connect Ti or RAx excess to the core.

Finds tiles with Ti or RAx excess (flow produced but not reaching the core)
and builds a conveyor/bridge chain from the excess tile to the core. Uses
the flow A* with Ax leakage banned to prevent mixing.
"""

from cambc import Controller, Direction, EntityType, Environment, Position
from flow_astar import AX, FlowAstar
from marker import TaskClaim, TaskKind
from util import TRANSPORT

from .build import Action, PlaceBridge, PlaceConveyor
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road
from .state import State


def connect_excess_ti_rax_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    best_tile: tuple[int, int] | None = None
    best_dist = 999999
    w = state.w
    f = state.my_flow
    own_harvesters = state.my_harvesters & state.my_built_harvesters
    for i in own_harvesters | state.my_transport | state.my_foundries:
        ti_ex = f.ti_excess[i]
        rax_ex = f.rax_excess[i]
        if (ti_ex > 0.01 or rax_ex > 0.01) and not is_claimed(
            state,
            i,
            TaskKind.FIX_EXCESS,
        ):
            x, y = i % w, i // w
            dist = (pos.x - x) ** 2 + (pos.y - y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_tile = (x, y)
    if best_tile is None:
        return None

    idx = state.idx(best_tile[0], best_tile[1])
    rnd = ct.get_current_round()
    state.claim = TaskClaim(TaskKind.FIX_EXCESS, idx, rnd)
    state.debug_target = (Position(best_tile[0], best_tile[1]), 255, 0, 0)

    sx, sy = best_tile
    si = state.idx(sx, sy)
    ent = state.entity[si]

    if ent is not None:
        etype = ent[0]
        if etype in (EntityType.HARVESTER, EntityType.FOUNDRY):
            cx, cy = state.my_core
            start = None
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
                nent = state.entity[ni]
                if nent is not None and nent[0] in TRANSPORT:
                    continue
                d = (nx - cx) ** 2 + (ny - cy) ** 2
                if d < best_d:
                    best_d = d
                    start = (nx, ny)
            if start is None:
                return None
            sx, sy = start
        elif etype in TRANSPORT:
            d = state.direction[si]
            bt = state.bridge_target[si]
            if d is not None:
                ddx, ddy = d.delta()
                ox, oy = sx + ddx, sy + ddy
                if state.in_bounds(ox, oy):
                    sx, sy = ox, oy
            elif bt is not None:
                sx, sy = bt

    start = (sx, sy)
    path = state.ti_cached_path
    if path is None or state.ti_cached_source != start:
        if state.ti_flow_search is None or state.ti_cached_source != start:
            state.ti_flow_search = FlowAstar(
                state,
                sx,
                sy,
                state.my_core_tiles,
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
        pent = state.entity[pi]
        if pent is not None and pent[1] == state.my_team:
            ptype = pent[0]
            if ptype == EntityType.CORE:
                continue
            if ptype in TRANSPORT:
                td = state.direction[pi]
                bt = state.bridge_target[pi]
                if td is not None:
                    ddx, ddy = td.delta()
                    if (x + ddx, y + ddy) == (nx, ny):
                        continue
                elif bt is not None and bt == (nx, ny):
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
