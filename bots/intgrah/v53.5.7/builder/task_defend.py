from building import (
    Building,
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, GameConstants, Position
from util import DIR4, DIR8

from builder.helpers import move_random, try_place
from builder.state import State


def _is_precious_friendly(b: Building | None, team: object) -> bool:
    if b is None or getattr(b, "team", None) != team:
        return False
    return isinstance(b, BuildingHarvester | BuildingFoundry | BuildingLauncher)


def _is_turret(b: Building | None) -> bool:
    match b:
        case BuildingGunner() | BuildingSentinel():
            return True
        case _:
            return False


def _is_turret_or_transport(b: Building | None) -> bool:
    match b:
        case (
            BuildingGunner()
            | BuildingSentinel()
            | BuildingConveyor()
            | BuildingArmouredConveyor()
            | BuildingSplitter()
            | BuildingBridge()
        ):
            return True
        case _:
            return False


def gunner_facing(state: State, ct: Controller, position: Position) -> Direction | None:
    if position not in state.adjacent_to_harvester:
        return None
    if not state.is_buildable(position):
        return None
    b = state.get_building(position)
    if _is_turret(b) or _is_precious_friendly(b, ct.get_team()):
        return None
    if not state.in_bounds(position) or not ct.is_in_vision(position):
        return None
    builder = ct.get_tile_builder_bot_id(position)
    if builder is not None and builder != ct.get_id():
        return None
    for d in DIR8:
        match state.get_building(position.add(d)):
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                for harvester_direction in DIR4:
                    if harvester_direction != d:
                        match state.get_building(position.add(harvester_direction)):
                            case BuildingHarvester():
                                return d
    return None


def sentinel_facing(
    state: State, ct: Controller, position: Position
) -> Direction | None:
    b = state.get_building(position)
    if (
        not state.nearest_enemy_turret
        or position.distance_squared(state.nearest_enemy_turret)
        > GameConstants.SENTINEL_VISION_RADIUS_SQ
        or position not in state.adjacent_to_harvester
        or not state.is_buildable(position)
        or _is_turret_or_transport(b)
        or _is_precious_friendly(b, ct.get_team())
        or not state.in_bounds(position)
        or not ct.is_in_vision(position)
    ):
        return None
    builder = ct.get_tile_builder_bot_id(position)
    if builder is not None and builder != ct.get_id():
        return None

    d = position.direction_to(state.nearest_enemy_turret)
    found_harvester = False
    for harvester_direction in DIR4:
        if harvester_direction != d:
            match state.get_building(position.add(harvester_direction)):
                case BuildingHarvester():
                    found_harvester = True
    if not found_harvester:
        return None

    shootable_tiles = ct.get_attackable_tiles_from(position, d, EntityType.SENTINEL)
    if state.nearest_enemy_turret in shootable_tiles:
        return d
    return None


def place_sentinel_nearby(state: State, ct: Controller) -> bool:
    my_pos = ct.get_position()
    for d in DIR8:
        test_position = my_pos.add(d)
        result = sentinel_facing(state, ct, test_position)
        if result is not None:
            return try_place(ct, EntityType.SENTINEL, test_position, result)
    result = sentinel_facing(state, ct, my_pos)
    if result and move_random(state, ct):
        try_place(ct, EntityType.SENTINEL, my_pos, result)
        return True
    return False


def place_gunner_nearby(state: State, ct: Controller) -> bool:
    my_pos = ct.get_position()
    for d in DIR8:
        test_position = my_pos.add(d)
        result = gunner_facing(state, ct, test_position)
        if result is not None:
            return try_place(ct, EntityType.GUNNER, test_position, result)
    result = gunner_facing(state, ct, my_pos)
    if result and move_random(state, ct):
        try_place(ct, EntityType.GUNNER, my_pos, result)
        return True
    return place_sentinel_nearby(state, ct)
