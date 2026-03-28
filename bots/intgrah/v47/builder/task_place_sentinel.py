from building import BuildingMarker, BuildingRoad, BuildingSentinel
from cambc import Controller, Direction, Environment, Position
from util import DELTA_TO_DIR, DIR4_DELTA, DIR8, DIR8_DELTA, INF, rotate_cw

from .build import Action, PlaceSentinel
from .helpers import move_toward_with_road
from .state import State


def _has_friendly_sentinel_near(state: State, hx: int, hy: int) -> bool:
    for dx, dy in DIR8_DELTA:
        nx, ny = hx + dx, hy + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        bld = state.building[ni]
        match bld:
            case BuildingSentinel(team=team) if team == state.my_team:
                return True
    return False


def _find_target(
    state: State,
) -> tuple[Position, Position, Direction, Direction] | None:
    pos = state.pos
    best = None
    best_dist = INF
    for hp in state.en_harvesters:
        hi = state.idx(hp.x, hp.y)
        if state.env[hi] != Environment.ORE_TITANIUM:
            continue
        hx, hy = hp.x, hp.y
        if _has_friendly_sentinel_near(state, hx, hy):
            continue
        for dx, dy in DIR4_DELTA:
            sx, sy = hx + dx, hy + dy
            if not state.in_bounds(sx, sy):
                continue
            si = state.idx(sx, sy)
            bld = state.building[si]
            match bld:
                case None:
                    pass
                case BuildingRoad(team=team) | BuildingMarker(team=team) if (
                    team == state.my_team
                ):
                    pass
                case _:
                    continue
            card_dir = DELTA_TO_DIR[(dx, dy)]
            facing = rotate_cw(card_dir, 3)
            facing_alt = rotate_cw(card_dir, 5)
            dist = abs(pos.x - sx) + abs(pos.y - sy)
            if dist < best_dist:
                best_dist = dist
                best = (Position(hx, hy), Position(sx, sy), facing, facing_alt)
    return best


def _is_in_sentinel_arc(
    sentinel_pos: Position,
    facing: Direction,
    pos: Position,
) -> bool:
    dx, dy = pos.x - sentinel_pos.x, pos.y - sentinel_pos.y
    if dx == 0 and dy == 0:
        return True
    fdx, fdy = facing.delta()
    for ddx in range(fdx - 1, fdx + 2):
        for ddy in range(fdy - 1, fdy + 2):
            if (ddx, ddy) == (dx, dy):
                return True
    return False


def place_sentinel(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target = _find_target(state)
    if target is None:
        return None
    _, sentinel_pos, facing, facing_alt = target
    pos = state.pos

    if pos == sentinel_pos:
        for d in DIR8:
            if not ct.can_move(d):
                continue
            new_pos = pos.add(d)
            if _is_in_sentinel_arc(sentinel_pos, facing, new_pos):
                continue
            if _is_in_sentinel_arc(sentinel_pos, facing_alt, new_pos):
                continue
            if ct.can_build_sentinel(sentinel_pos, facing):
                return d, PlaceSentinel(sentinel_pos, facing)
            if ct.can_build_sentinel(sentinel_pos, facing_alt):
                return d, PlaceSentinel(sentinel_pos, facing_alt)
        for d in DIR8:
            if ct.can_move(d):
                if ct.can_build_sentinel(sentinel_pos, facing):
                    return d, PlaceSentinel(sentinel_pos, facing)
                if ct.can_build_sentinel(sentinel_pos, facing_alt):
                    return d, PlaceSentinel(sentinel_pos, facing_alt)
        return None

    if pos.distance_squared(sentinel_pos) <= 2:
        bid = ct.get_tile_building_id(sentinel_pos)
        if bid is not None and ct.can_destroy(sentinel_pos):
            ct.destroy(sentinel_pos)
        if ct.can_build_sentinel(sentinel_pos, facing):
            return Direction.CENTRE, PlaceSentinel(sentinel_pos, facing)
        if ct.can_build_sentinel(sentinel_pos, facing_alt):
            return Direction.CENTRE, PlaceSentinel(sentinel_pos, facing_alt)

    move, build = move_toward_with_road(state, ct, sentinel_pos)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(sentinel_pos) <= 2 and new_pos != sentinel_pos:
            bid = ct.get_tile_building_id(sentinel_pos)
            if bid is not None and ct.can_destroy(sentinel_pos):
                ct.destroy(sentinel_pos)
            if ct.can_build_sentinel(sentinel_pos, facing):
                build = PlaceSentinel(sentinel_pos, facing)
            elif ct.can_build_sentinel(sentinel_pos, facing_alt):
                build = PlaceSentinel(sentinel_pos, facing_alt)
    state.debug_target = (sentinel_pos, 255, 0, 0)
    return move, build
