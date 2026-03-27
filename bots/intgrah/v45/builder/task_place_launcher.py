from cambc import Controller, Direction, EntityType, Position
from util import DIR8_DELTA

from .build import Action, PlaceLauncher
from .helpers import move_toward_with_road
from .state import COST_IMPASSABLE, State


def _undefended_bridge(state: State) -> tuple[int, int] | None:
    for p in state.my_transport:
        i = state.idx(p.x, p.y)
        ent = state.entity[i]
        if ent is None or ent[0] != EntityType.BRIDGE:
            continue
        bx, by = p.x, p.y
        has_launcher = False
        for dx, dy in DIR8_DELTA:
            nx, ny = bx + dx, by + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = state.idx(nx, ny)
            nent = state.entity[ni]
            if (
                nent is not None
                and nent[0] == EntityType.LAUNCHER
                and nent[1] == state.my_team
            ):
                has_launcher = True
                break
        if not has_launcher:
            return (bx, by)
    return None


def _find_placement(
    state: State,
    bx: int,
    by: int,
) -> Position | None:
    for dx, dy in DIR8_DELTA:
        ax, ay = bx + dx, by + dy
        if not state.in_bounds(ax, ay):
            continue
        ai = state.idx(ax, ay)
        ent = state.entity[ai]
        if ent is not None and ent[0] not in (EntityType.ROAD, EntityType.MARKER):
            continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        return Position(ax, ay)
    return None


def place_launcher(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    bridge = _undefended_bridge(state)
    if bridge is None:
        return None
    bx, by = bridge
    spot = _find_placement(state, bx, by)
    if spot is None:
        return None
    ax, ay = spot
    adj = Position(ax, ay)
    pos = state.pos

    if pos.distance_squared(adj) <= 2:
        bid = ct.get_tile_building_id(adj)
        if bid is not None and ct.can_destroy(adj):
            ct.destroy(adj)
        if ct.can_build_launcher(adj):
            return Direction.CENTRE, PlaceLauncher(adj)

    move, build = move_toward_with_road(state, ct, adj)
    if move == Direction.CENTRE and build is None:
        return None
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(adj) <= 2:
            bid = ct.get_tile_building_id(adj)
            if bid is not None and ct.can_destroy(adj):
                ct.destroy(adj)
            if ct.can_build_launcher(adj):
                build = PlaceLauncher(adj)
    state.debug_target = (adj, 255, 165, 0)
    return move, build
