from building import BuildingHarvester, BuildingSentinel
from cambc import Controller, Direction, Position
from util import DIR8_DELTA, INF

from .action import Action, PlaceBarrier
from .helpers import move_toward_with_road
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
    unharvested = state.ore_ti - state.my_harvesters - state.en_harvesters
    if not unharvested:
        return None
    pos = state.pos
    best: Position | None = None
    best_dist = INF
    for ox, oy in unharvested:
        oi = state.idx(ox, oy)
        op = Position(ox, oy)
        if op in state.my_barriers or op in state.en_barriers:
            continue
        bld = state.building[oi]
        match bld:
            case BuildingHarvester():
                continue
        if not _has_friendly_sentinel_adjacent(state, ox, oy):
            continue
        dist = abs(pos.x - ox) + abs(pos.y - oy)
        if dist < best_dist:
            best_dist = dist
            best = Position(ox, oy)
    return best


def barrier_ore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
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
        return Direction.CENTRE, PlaceBarrier(ore_pos)

    move, build = move_toward_with_road(state, ct, ore_pos)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(ore_pos) <= 2 and new_pos != ore_pos:
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None and ct.can_destroy(ore_pos):
                ct.destroy(ore_pos)
            build = PlaceBarrier(ore_pos)
    ct.draw_indicator_line(state.pos, ore_pos, 128, 128, 128)
    return move, build
