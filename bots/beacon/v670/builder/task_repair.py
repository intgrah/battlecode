from building import BuildingRoad
from cambc import Controller, Environment, Position
from util import closest

from .state import State


def is_dangling(state: State, ct: Controller, pos: Position) -> bool:
    if not state.in_bounds(pos):
        return False

    i = pos.y * state.w + pos.x
    b = state.buildings[i]
    if b is None:
        if state.env[i] == Environment.WALL:
            return False

    elif not isinstance(b, BuildingRoad) or b.team != ct.get_team():
        return False

    if state.conveyors_to_here[i]:
        return True

    return pos in state.adjacent_to_unconnected_harvester


def is_valid_loose_end_target(state: State, ct: Controller, pos: Position) -> bool:
    if not is_dangling(state, ct, pos):
        return False

    my_id = ct.get_id()
    if ct.is_in_vision(pos):
        bid = ct.get_tile_builder_bot_id(pos)
        friendly = ct.get_team(bid) == ct.get_team()
        if bid is not None and bid != my_id and friendly:
            return False

    leading = state.get_conveyors_to_here(pos)
    for lpos in leading:
        if not ct.is_in_vision(lpos):
            continue
        lbid = ct.get_tile_builder_bot_id(lpos)
        friendly = ct.get_team(lbid) == ct.get_team()
        if lbid is not None and lbid != my_id and friendly:
            return False
    return True


def find_dangling(state: State, ct: Controller) -> Position | None:
    vision_radius = ct.get_vision_radius_sq()
    nearby = ct.get_nearby_tiles(vision_radius)

    candidates = [pos for pos in nearby if is_valid_loose_end_target(state, ct, pos)]

    if not candidates:
        return None

    my_pos = ct.get_position()
    return closest(my_pos, candidates)
