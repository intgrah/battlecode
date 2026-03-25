from dataclasses import dataclass
from enum import Enum, auto

from cambc import Controller, Direction, Position


class Task(Enum):
    FIX_EXCESS = auto()
    HARVEST_TI = auto()
    HARVEST_AX = auto()
    RAID = auto()
    EXPLORE = auto()
    PATROL = auto()
    NAV_ENEMY_CORE = auto()
    PLACE_FOUNDRY = auto()
    FIX_EXCESS_AX = auto()


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


type Action = (
    PlaceHarvester
    | PlaceConveyor
    | PlaceBridge
    | PlaceRoad
    | PlaceFoundry
    | PlaceSplitter
    | SelfDestruct
    | Heal
)


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    bid = ct.get_tile_building_id(pos)
    if bid is not None and ct.get_team(bid) == ct.get_team():
        ct.destroy(pos)


def execute(action: Action, ct: Controller) -> None:
    ti, _ = ct.get_global_resources()
    match action:
        case PlaceHarvester(pos):
            cost, _ = ct.get_harvester_cost()
            if ti >= cost and ct.can_build_harvester(pos):
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
