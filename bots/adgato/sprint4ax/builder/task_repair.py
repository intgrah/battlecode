from building import *
from cambc import Controller, Environment, Position
from util import closest

from .state import State


def is_dangling(state: State, ct: Controller, pos: Position) -> bool:
    if not state.in_bounds(pos):
        return False

    print(f"checking {pos} dangling")

    i = pos.y * state.w + pos.x
    b = state.buildings[i]
    if b is None:
        print("i'm empty")
        if state.env[i] == Environment.WALL:
            return False

    else:
        print("i'm a building")
        if b.team != ct.get_team():
            return False

        match b:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                print("i'm a friendly conveyor")
                adj = pos.add(d)
                if not state.in_bounds(adj):
                    return True
                j = adj.y * state.w + adj.x
                c = state.buildings[j]
                if c is None:
                    print("conveyor points to nothing")
                    return state.env[j] == Environment.WALL
                if c.team != ct.get_team():
                    return True
                match c:
                    case BuildingBarrier() | BuildingLauncher():
                        print("conveyor points to blocked")
                        return True
                    case (
                        BuildingConveyor(direction=d2)
                        | BuildingArmouredConveyor(direction=d2)
                    ) if d == d2.opposite():
                        print("conveyor points to opposing")
                        return True
                    case BuildingHarvester():
                        print("conveyor points to harvester")
                        return pos in state.adjacent_to_unconnected_harvester
                    case _:
                        print("conveyor points to infra")
                        return False
            case BuildingRoad():
                print("i'm a road")
            case _:
                print("i'm infra")
                return False

    if state.conveyors_to_here[i]:
        print("conveyors lead to me")
        return True

    print("am i adjacent to a harvester")
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
