from cambc import Controller, Direction, EntityType, Position
from marker import TaskKind
from util import DELTA_TO_DIR, DIR4_DELTA, DIR8, DIR8_DELTA

from .build import Action, PlaceBarrier, PlaceSentinel
from .helpers import is_claimed, move_toward_with_road
from .state import COST_IMPASSABLE, State
from .task_secure_ore import _best_ore as _secure_best_ore

DIR8_IDX = {d: i for i, d in enumerate(DIR8)}


def _rotate_cw(d: Direction, steps: int) -> Direction:
    return DIR8[(DIR8_IDX[d] + steps) % 8]


def _best_deny_target(
    state: State,
    exclude: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    unharvested = state.ore_ti - state.my_harvested
    if not unharvested:
        return None
    pos = state.pos
    best = None
    best_dist = 999999
    cx, cy = state.my_core
    half = (state.w + state.h) // 4
    for ox, oy in unharvested:
        if exclude is not None and (ox, oy) == exclude:
            continue
        core_dist = abs(ox - cx) + abs(oy - cy)
        if core_dist <= half:
            continue
        oi = state.idx(ox, oy)
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            continue
        if (
            Position(ox, oy) in state.my_barriers
            or Position(ox, oy) in state.en_barriers
        ):
            continue
        dist = abs(pos.x - ox) + abs(pos.y - oy)
        en_core = state.en_core
        if en_core is not None:
            en_dist = abs(en_core[0] - ox) + abs(en_core[1] - oy)
            score = en_dist * 2 + dist
        else:
            score = dist
        if score < best_dist:
            best_dist = score
            best = (ox, oy)
    return best


def _has_friendly_sentinel_near(state: State, ox: int, oy: int) -> bool:
    for dx, dy in DIR8_DELTA:
        nx, ny = ox + dx, oy + dy
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


def deny_enemy_harvester(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    secure_target = _secure_best_ore(state)
    target = _best_deny_target(state, exclude=secure_target)
    if target is None:
        return None
    ox, oy = target
    oi = state.idx(ox, oy)
    ore_pos = Position(ox, oy)
    pos = state.pos

    ent = state.entity[oi]
    has_enemy_harvester = (
        ent is not None and ent[0] == EntityType.HARVESTER and ent[1] != state.my_team
    )

    if has_enemy_harvester and not _has_friendly_sentinel_near(state, ox, oy):
        for dx, dy in DIR4_DELTA:
            sx, sy = ox + dx, oy + dy
            if not state.in_bounds(sx, sy):
                continue
            si = state.idx(sx, sy)
            sent = state.entity[si]
            if sent is not None and sent[0] not in (EntityType.ROAD, EntityType.MARKER):
                continue
            if state.walkable(sx, sy) >= COST_IMPASSABLE:
                if (
                    sent is not None
                    and sent[0] == EntityType.ROAD
                    and sent[1] == state.my_team
                ):
                    pass
                else:
                    continue
            sentinel_pos = Position(sx, sy)
            card_dir = DELTA_TO_DIR[(dx, dy)]
            facing_cw3 = _rotate_cw(card_dir, 3)
            facing_cw5 = _rotate_cw(card_dir, 5)

            if pos.distance_squared(sentinel_pos) <= 2 and pos != sentinel_pos:
                bid = ct.get_tile_building_id(sentinel_pos)
                if bid is not None and ct.can_destroy(sentinel_pos):
                    ct.destroy(sentinel_pos)
                if ct.can_build_sentinel(sentinel_pos, facing_cw3):
                    return Direction.CENTRE, PlaceSentinel(sentinel_pos, facing_cw3)
                if ct.can_build_sentinel(sentinel_pos, facing_cw5):
                    return Direction.CENTRE, PlaceSentinel(sentinel_pos, facing_cw5)

            move, build = move_toward_with_road(state, ct, sentinel_pos)
            if move != Direction.CENTRE and build is None:
                new_pos = pos.add(move)
                if (
                    new_pos.distance_squared(sentinel_pos) <= 2
                    and new_pos != sentinel_pos
                ):
                    bid = ct.get_tile_building_id(sentinel_pos)
                    if bid is not None and ct.can_destroy(sentinel_pos):
                        ct.destroy(sentinel_pos)
                    if ct.can_build_sentinel(sentinel_pos, facing_cw3):
                        build = PlaceSentinel(sentinel_pos, facing_cw3)
                    elif ct.can_build_sentinel(sentinel_pos, facing_cw5):
                        build = PlaceSentinel(sentinel_pos, facing_cw5)
            state.debug_target = (sentinel_pos, 255, 0, 0)
            return move, build
        return None

    if pos.distance_squared(ore_pos) <= 2 and pos != ore_pos:
        bid = ct.get_tile_building_id(ore_pos)
        if bid is not None and ct.can_destroy(ore_pos):
            ct.destroy(ore_pos)
        if ct.can_build_barrier(ore_pos):
            return Direction.CENTRE, PlaceBarrier(ore_pos)

    move, build = move_toward_with_road(state, ct, ore_pos)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(ore_pos) <= 2 and new_pos != ore_pos:
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None and ct.can_destroy(ore_pos):
                ct.destroy(ore_pos)
            if ct.can_build_barrier(ore_pos):
                build = PlaceBarrier(ore_pos)
    state.debug_target = (ore_pos, 255, 128, 0)
    return move, build
