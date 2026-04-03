from action import ActionOnly, MoveAction, MoveOnly, PlaceBarrier, Turn
from building import BuildingHarvester, BuildingSentinel
from cambc import Controller, Position
from util import DIR8_DELTA

from .helpers import min_adjacent_dist, move_toward_with_road
from .state import State


def _has_friendly_sentinel_adjacent(state: State, ox: int, oy: int) -> bool:
    for dx, dy in DIR8_DELTA:
        nx, ny = ox + dx, oy + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        bld = state.building[ni]
        match bld:
            case BuildingSentinel(team=team) if team == state.my_team:
                return True
    return False


def _best_denied_ore(state: State) -> Position | None:
    unharvested = state.ore_ti - state.my_harvesters
    if not unharvested:
        return None
    w = state.w
    best: Position | None = None
    best_hops = -1
    for oi in unharvested:
        d = min_adjacent_dist(state, oi)
        if d == -1:
            continue
        ox, oy = oi % w, oi // w
        if oi in state.barriers:
            continue
        bld = state.building[oi]
        match bld:
            case BuildingHarvester():
                continue
        if not _has_friendly_sentinel_adjacent(state, ox, oy):
            continue
        if best is None or d < best_hops:
            best_hops = d
            best = Position(ox, oy)
    return best


def barrier_ore(
    state: State,
    ct: Controller,
) -> Turn | None:
    target = _best_denied_ore(state)
    if target is None:
        return None
    ox, oy = target
    ore_pos = Position(ox, oy)
    pos = state.pos

    if pos.distance_squared(ore_pos) <= 2 and pos != ore_pos:
        bid = ct.get_tile_building_id(ore_pos)
        if bid is not None and ct.can_destroy(ore_pos):
            ct.destroy(ore_pos)
        print(f"    barrier_ore: place at ({ox},{oy})")
        return ActionOnly(PlaceBarrier(ore_pos))

    result = move_toward_with_road(state, ct, ore_pos)
    match result:
        case None:
            return None
        case MoveOnly(move):
            new_pos = pos.add(move)
            if new_pos.distance_squared(ore_pos) <= 2 and new_pos != ore_pos:
                bid = ct.get_tile_building_id(ore_pos)
                if bid is not None and ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                result = MoveAction(move, PlaceBarrier(ore_pos))
    print(f"    barrier_ore: nav to ({ox},{oy})")
    ct.draw_indicator_dot(ore_pos, 128, 128, 128)
    return result
