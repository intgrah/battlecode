from cambc import Controller, Direction, EntityType, Position

from .build import Action, PlaceBarrier
from .helpers import move_toward_with_road
from .state import State


def _best_unbarriered_ore(state: State) -> tuple[int, int] | None:
    unharvested = state.ore_ti - state.my_harvested - state.en_harvested
    if not unharvested:
        return None
    pos = state.pos
    best = None
    best_dist = 999999
    for ox, oy in unharvested:
        oi = state.idx(ox, oy)
        if oi in state.my_barriers or oi in state.en_barriers:
            continue
        ent = state.entity[oi]
        if ent is not None and ent[0] == EntityType.HARVESTER:
            continue
        dist = abs(pos.x - ox) + abs(pos.y - oy)
        if dist < best_dist:
            best_dist = dist
            best = (ox, oy)
    return best


def barrier_ore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target = _best_unbarriered_ore(state)
    if target is None:
        return None
    ox, oy = target
    ore_pos = Position(ox, oy)
    pos = state.pos

    if pos.distance_squared(ore_pos) <= 2 and pos != ore_pos:
        bid = ct.get_tile_building_id(ore_pos)
        if bid is not None and ct.can_destroy(ore_pos):
            ct.destroy(ore_pos)
        return Direction.CENTRE, PlaceBarrier(ore_pos)

    move, build = move_toward_with_road(state, ct, ore_pos)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(ore_pos) <= 2 and new_pos != ore_pos:
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None and ct.can_destroy(ore_pos):
                ct.destroy(ore_pos)
            build = PlaceBarrier(ore_pos)
    state.debug_target = (ore_pos, 128, 128, 128)
    return move, build
