from dataclasses import dataclass
from enum import Enum, auto

from cambc import Controller, Direction, EntityType, Position


class Task(Enum):
    """High level Tasks"""

    CONNECT_EXCESS_TI_RAX_CORE = auto()
    HARVEST_TI = auto()
    HARVEST_AX = auto()
    RAID = auto()
    EXPLORE = auto()
    PATROL = auto()
    NAV_ENEMY_CORE = auto()
    PLACE_FOUNDRY_TI_CONV = auto()
    PLACE_FOUNDRY_MIXED_CONV = auto()
    PLACE_SPLITTER_FOUNDRY = auto()
    CONNECT_EXCESS_AX_TI_CONV = auto()
    HEAL_CORE = auto()
    SECURE_ORE = auto()
    PLACE_LAUNCHER = auto()
    DENY_ENEMY_HARVESTER = auto()
    CONNECT_EXCESS_TI_BRIDGE_CORE = auto()
    REPAIR_BRIDGE = auto()
    BARRIER_ORE = auto()
    FIRE_ENEMY_TRANSPORT = auto()
    PLACE_SENTINEL = auto()
    FORTIFY_ORE = auto()
    NAV_CENTER = auto()


# Low level Actions (one per turn)


@dataclass(frozen=True, slots=True)
class PlaceHarvester:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceConveyor:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceBridge:
    pos: Position
    target: Position


@dataclass(frozen=True, slots=True)
class PlaceRoad:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceFoundry:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceSplitter:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class SelfDestruct:
    pass


@dataclass(frozen=True, slots=True)
class Heal:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceBarrier:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceSentinel:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceLauncher:
    pos: Position


@dataclass(frozen=True, slots=True)
class Fire:
    pos: Position


type Action = (
    PlaceHarvester
    | PlaceConveyor
    | PlaceBridge
    | PlaceRoad
    | PlaceFoundry
    | PlaceSplitter
    | SelfDestruct
    | Heal
    | PlaceBarrier
    | PlaceSentinel
    | PlaceLauncher
    | Fire
)


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    bid = ct.get_tile_building_id(pos)
    if bid is not None and ct.get_team(bid) == ct.get_team():
        # Never destroy our own sentinels
        if ct.get_entity_type(bid) == EntityType.SENTINEL:
            return
        ct.destroy(pos)


def execute(action: Action, ct: Controller) -> None:
    ti, _ = ct.get_global_resources()
    match action:
        case PlaceHarvester(pos):
            cost, _ = ct.get_harvester_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_harvester(pos):
                    ct.build_harvester(pos)
        case PlaceConveyor(pos, direction):
            cost, _ = ct.get_conveyor_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_conveyor(pos, direction):
                    ct.build_conveyor(pos, direction)
        case PlaceBridge(pos, target):
            cost, _ = ct.get_bridge_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_bridge(pos, target):
                    ct.build_bridge(pos, target)
        case PlaceRoad(pos):
            cost, _ = ct.get_road_cost()
            if ti >= cost and ct.can_build_road(pos):
                ct.build_road(pos)
        case PlaceFoundry(pos):
            cost, _ = ct.get_foundry_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_foundry(pos):
                    ct.build_foundry(pos)
        case PlaceSplitter(pos, direction):
            cost, _ = ct.get_splitter_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_splitter(pos, direction):
                    ct.build_splitter(pos, direction)
        case SelfDestruct():
            ct.self_destruct()
        case Heal(pos):
            if ct.can_heal(pos):
                ct.heal(pos)
        case PlaceBarrier(pos):
            cost, _ = ct.get_barrier_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_barrier(pos):
                    ct.build_barrier(pos)
        case PlaceSentinel(pos, direction):
            cost, _ = ct.get_sentinel_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_sentinel(pos, direction):
                    ct.build_sentinel(pos, direction)
        case PlaceLauncher(pos):
            cost, _ = ct.get_launcher_cost()
            if ti >= cost:
                _destroy_friendly(ct, pos)
                if ct.can_build_launcher(pos):
                    ct.build_launcher(pos)
        case Fire(pos):
            if ct.can_fire(pos):
                ct.fire(pos)
