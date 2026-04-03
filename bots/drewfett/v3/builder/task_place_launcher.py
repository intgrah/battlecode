from building import BuildingLauncher, BuildingMarker, BuildingRoad
from cambc import Controller, Direction, Position
from util import COST_IMPASSABLE, DIR8_DELTA

from .action import Action, PlaceLauncher
from .helpers import move_toward_with_road
from .state import State


def _undefended_transport(state: State) -> tuple[int, int] | None:
    w = state.w
    for idx in state.transport:
        bx, by = idx % w, idx // w
        has_launcher = False
        for dx, dy in DIR8_DELTA:
            nx, ny = bx + dx, by + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = state.idx(nx, ny)
            nbld = state.building[ni]
            match nbld:
                case BuildingLauncher(team=team) if team == state.my_team:
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
        bld = state.building[ai]
        match bld:
            case None | BuildingRoad() | BuildingMarker():
                pass
            case _:
                continue
        if state.walkable(ax, ay) >= COST_IMPASSABLE:
            continue
        return Position(ax, ay)
    return None


def place_launcher(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    bridge = _undefended_transport(state)
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

    result = move_toward_with_road(state, ct, adj)
    if result is None:
        return None
    move, build = result
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
    ct.draw_indicator_line(state.pos, adj, 255, 165, 0)
    return move, build
