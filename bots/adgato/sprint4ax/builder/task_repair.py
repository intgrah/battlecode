from building import *
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
    else:
        if b.team != ct.get_team():
            return False

        match b:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                adj = pos.add(d)
                if state.in_bounds(adj):
                    j = adj.y * state.w + adj.x
                    c = state.buildings[j]
                    if c is None:
                        if state.env[j] != Environment.WALL:
                            return False
                    elif c.team == ct.get_team():
                        match c:
                            case (
                                BuildingBarrier()
                                | BuildingLauncher()
                                | BuildingHarvester()
                            ):
                                pass
                            case (
                                BuildingConveyor(direction=d2)
                                | BuildingArmouredConveyor(direction=d2)
                            ) if d == d2.opposite():
                                pass
                            case _:
                                return False
            case BuildingRoad():
                pass
            case _:
                return False

    return state.conveyors_to_here[i] or pos in state.adjacent_to_unconnected_harvester


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
