from bridge_astar import BridgeFlowAstar
from cambc import Controller, Direction, EntityType, Position
from flow_astar import AX

from .build import Action, PlaceBridge
from .helpers import cardinal_adjacent, move_toward_with_road
from .state import State


def _find_broken_bridge(state: State) -> tuple[int, int] | None:
    w = state.w
    for bi in state.my_transport:
        ent = state.entity[bi]
        if ent is None or ent[0] != EntityType.BRIDGE:
            continue
        bt = state.bridge_target[bi]
        if bt is None:
            continue
        ti = bt[1] * w + bt[0]
        tent = state.entity[ti]
        if tent is not None:
            if tent[0] == EntityType.BRIDGE and tent[1] == state.my_team:
                continue
            if tent[0] == EntityType.CORE and tent[1] == state.my_team:
                continue
        return bt
    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w
        has_adj_bridge = False
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = state.idx(nx, ny)
            nent = state.entity[ni]
            if (
                nent is not None
                and nent[0] == EntityType.BRIDGE
                and nent[1] == state.my_team
            ):
                has_adj_bridge = True
                break
        if not has_adj_bridge:
            cx, cy = state.my_core
            best_d = 999999
            best_spot = None
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = hx + dx, hy + dy
                if not state.in_bounds(nx, ny):
                    continue
                d = abs(nx - cx) + abs(ny - cy)
                if d < best_d:
                    best_d = d
                    best_spot = (nx, ny)
            if best_spot is not None:
                return best_spot
    return None


def repair_bridge(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    broken = _find_broken_bridge(state)
    if broken is None:
        return None
    bx, by = broken
    bridge_pos = Position(bx, by)
    pos = state.pos

    search = BridgeFlowAstar(state, bx, by, state.my_core_tiles, AX)
    search.set_budget(ct, 800)
    search.compute()
    path = search.get_path()
    if path is None or len(path) < 2:
        return None
    w = state.w
    nx, ny = path[1] % w, path[1] // w
    target_pos = Position(nx, ny)

    if pos.distance_squared(bridge_pos) <= 2 and pos != bridge_pos:
        bid = ct.get_tile_building_id(bridge_pos)
        if bid is not None and ct.can_destroy(bridge_pos):
            ct.destroy(bridge_pos)
        return Direction.CENTRE, PlaceBridge(bridge_pos, target_pos)

    adj = cardinal_adjacent(state, pos, bridge_pos)
    if adj is None:
        return None
    move, build = move_toward_with_road(state, ct, adj)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(bridge_pos) <= 2 and new_pos != bridge_pos:
            bid = ct.get_tile_building_id(bridge_pos)
            if bid is not None and ct.can_destroy(bridge_pos):
                ct.destroy(bridge_pos)
            build = PlaceBridge(bridge_pos, target_pos)
    state.debug_target = (bridge_pos, 255, 0, 255)
    return move, build
