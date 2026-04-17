from __future__ import annotations

from typing import TYPE_CHECKING

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
from cambc import Controller, EntityType, GameConstants, Direction, Team
from util import DIR4, DIR8, DELTA_TO_DIR, get_direction_object

from .helpers import move_random, try_place

if TYPE_CHECKING:
    from builder import Builder, PosInt


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


def _is_precious_friendly(b: Building | None, team: Team) -> bool:
    """True if `b` is a friendly building we must NOT destroy when
    placing a turret. Destroying conveyors / roads / markers / enemy
    stuff is fine — they're cheap or hostile — but stomping our own
    harvester wipes ore output, and stomping our own foundry /
    launcher kills a huge Ti + scaling investment."""
    if b is None or getattr(b, "team", None) != team:
        return False
    return isinstance(b, BuildingHarvester | BuildingFoundry | BuildingLauncher)


def gunner_facing(self: Builder, ct: Controller, position: PosInt) -> Direction | None:
    if position not in self.adjacent_to_harvester:
        return None
    if not self.is_buildable(position):
        return None
    # try_place destroys whatever's on the tile before building.
    # Fine for roads/conveyors/markers, but never stomp our own
    # harvester / foundry / launcher — too expensive to replace.
    b = self.get_building(position)
    if _is_precious_friendly(b, self.my_team):
        return None
    if _is_turret(b):
        return None
    if not self.in_bounds(position) or not ct.is_in_vision(self.pos(position)):
        return None
    builder = ct.get_tile_builder_bot_id(self.pos(position))
    if builder is not None and builder != self.my_id:
        return None
    for d in DIR8:
        match self.get_building(position + d):
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != self.my_team
            ):
                for harvester_direction in DIR4:
                    if harvester_direction != d:
                        match self.get_building(position + harvester_direction):
                            case BuildingHarvester():
                                return DELTA_TO_DIR[d]
    return None


def sentinel_facing(
    self: Builder, ct: Controller, position: PosInt
) -> Direction | None:
    b = self.get_building(position)
    if (
        not self.nearest_enemy_turret
        or self.sq_dist(position, self.nearest_enemy_turret)
        > GameConstants.SENTINEL_VISION_RADIUS_SQ
        or position not in self.adjacent_to_harvester
        or not self.is_buildable(position)
        or _is_turret_or_transport(b)
        or _is_precious_friendly(b, self.my_team)
        or not self.in_bounds(position)
        or not ct.is_in_vision(self.pos(position))
    ):
        return None
    builder = ct.get_tile_builder_bot_id(self.pos(position))
    if builder is not None and builder != self.my_id:
        return None

    d = get_direction_object(position, self.nearest_enemy_turret)
    found_harvester = False
    for harvester_direction in DIR4:
        if harvester_direction != d:
            match self.get_building(position + harvester_direction):
                case BuildingHarvester():
                    found_harvester = True
    if not found_harvester:
        return None

    shootable_tiles = ct.get_attackable_tiles_from(self.pos(position), d, EntityType.SENTINEL)
    if self.nearest_enemy_turret in shootable_tiles:
        return d
    return None


def place_sentinel_nearby(self: Builder, ct: Controller) -> bool:
    my_pos = self.my_pos
    for d in DIR8:
        test_position = my_pos + d
        result = sentinel_facing(self, ct, test_position)
        if result is not None:
            return try_place(ct, EntityType.SENTINEL, self.pos(test_position), result)
    result = sentinel_facing(self, ct, my_pos)
    if result and move_random(self, ct):
        try_place(ct, EntityType.SENTINEL, self.pos(my_pos), result)
        return True
    return False


def place_gunner_nearby(self: Builder, ct: Controller) -> bool:
    my_pos = self.my_pos
    for d in DIR8:
        test_position = my_pos + d
        result = gunner_facing(self, ct, test_position)
        if result is not None:
            return try_place(ct, EntityType.GUNNER, self.pos(test_position), result)
    result = gunner_facing(self, ct, my_pos)
    if result and move_random(self, ct):
        try_place(ct, EntityType.GUNNER, self.pos(my_pos), result)
        return True
    return place_sentinel_nearby(self, ct)
