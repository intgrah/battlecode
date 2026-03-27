from cambc import Controller, Direction, EntityType, Position
from util import DELTA_TO_DIR, DIR4_DELTA, DIR8, DIR8_DELTA

from .build import Action, PlaceSentinel
from .helpers import move_toward_with_road
from .state import State

_DIRS_CW = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
_DIRS_CW_IDX = {d: i for i, d in enumerate(_DIRS_CW)}


def _rotate_cw(d: Direction, steps: int) -> Direction:
    return _DIRS_CW[(_DIRS_CW_IDX[d] + steps) % 8]


def _has_friendly_sentinel_near(state: State, hx: int, hy: int) -> bool:
    for dx, dy in DIR8_DELTA:
        nx, ny = hx + dx, hy + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        ent = state.entity[ni]
        if (
            ent is not None
            and ent[0] == EntityType.SENTINEL
            and ent[1] == state.my_team
        ):
            return True
    return False


def _find_target(
    state: State,
) -> tuple[tuple[int, int], tuple[int, int], Direction, Direction] | None:
    w = state.w
    pos = state.pos
    best = None
    best_dist = 999999
    for hi in state.en_harvesters:
        hx, hy = hi % w, hi // w
        if _has_friendly_sentinel_near(state, hx, hy):
            continue
        for dx, dy in DIR4_DELTA:
            sx, sy = hx + dx, hy + dy
            if not state.in_bounds(sx, sy):
                continue
            si = state.idx(sx, sy)
            ent = state.entity[si]
            if ent is not None:
                if (
                    ent[0] in (EntityType.ROAD, EntityType.MARKER)
                    and ent[1] == state.my_team
                ) or ent[0] is None:
                    pass
                else:
                    continue
            card_dir = DELTA_TO_DIR[(dx, dy)]
            facing = _rotate_cw(card_dir, 3)
            facing_alt = _rotate_cw(card_dir, 5)
            dist = abs(pos.x - sx) + abs(pos.y - sy)
            if dist < best_dist:
                best_dist = dist
                best = ((hx, hy), (sx, sy), facing, facing_alt)
    return best


def _is_in_sentinel_arc(
    sentinel_pos: tuple[int, int],
    facing: Direction,
    pos: Position,
) -> bool:
    sx, sy = sentinel_pos
    dx, dy = pos.x - sx, pos.y - sy
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
    _, (sx, sy), facing, facing_alt = target
    sentinel_pos = Position(sx, sy)
    pos = state.pos

    if pos == sentinel_pos:
        for d in DIR8:
            if not ct.can_move(d):
                continue
            new_pos = pos.add(d)
            if _is_in_sentinel_arc((sx, sy), facing, new_pos):
                continue
            if _is_in_sentinel_arc((sx, sy), facing_alt, new_pos):
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
