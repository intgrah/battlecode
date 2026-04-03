from dataclasses import dataclass

from cambc import Controller, Direction, EntityType, Position

__all__ = [
    "Action",
    "ActionMove",
    "ActionOnly",
    "Fire",
    "Heal",
    "MoveAction",
    "MoveOnly",
    "PlaceArmouredConveyor",
    "PlaceBarrier",
    "PlaceBridge",
    "PlaceConveyor",
    "PlaceFoundry",
    "PlaceGunner",
    "PlaceHarvester",
    "PlaceLauncher",
    "PlaceRoad",
    "PlaceSentinel",
    "PlaceSplitter",
    "SelfDestruct",
    "Turn",
    "can_execute",
    "execute",
]


@dataclass(frozen=True, slots=True)
class PlaceHarvester:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceConveyor:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceArmouredConveyor:
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
class PlaceGunner:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class Fire:
    pass


type Action = (
    PlaceHarvester
    | PlaceConveyor
    | PlaceArmouredConveyor
    | PlaceBridge
    | PlaceRoad
    | PlaceFoundry
    | PlaceSplitter
    | SelfDestruct
    | Heal
    | PlaceBarrier
    | PlaceSentinel
    | PlaceLauncher
    | PlaceGunner
    | Fire
)


@dataclass(frozen=True, slots=True)
class ActionOnly:
    action: Action


@dataclass(frozen=True, slots=True)
class MoveOnly:
    move: Direction


@dataclass(frozen=True, slots=True)
class ActionMove:
    action: Action
    move: Direction


@dataclass(frozen=True, slots=True)
class MoveAction:
    move: Direction
    action: Action


type Turn = ActionOnly | MoveOnly | ActionMove | MoveAction


def _would_destroy_clear(ct: Controller, pos: Position) -> bool:
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return True
    if ct.get_team(bid) != ct.get_team():
        return False
    return ct.get_entity_type(bid) in (EntityType.ROAD, EntityType.MARKER)


def can_execute(action: Action, ct: Controller) -> bool:
    """
    Specification: can_execute is True iff execute does not raise.
    Accounts for _destroy_friendly clearing roads/markers before building.
    """
    ti, _ = ct.get_global_resources()
    match action:
        case PlaceHarvester(pos):
            cost, _ = ct.get_harvester_cost()
            return ti >= cost and (
                ct.can_build_harvester(pos) or _would_destroy_clear(ct, pos)
            )
        case PlaceConveyor(pos, direction):
            cost, _ = ct.get_conveyor_cost()
            return ti >= cost and (
                ct.can_build_conveyor(pos, direction) or _would_destroy_clear(ct, pos)
            )
        case PlaceArmouredConveyor(pos, direction):
            cost, _ = ct.get_armoured_conveyor_cost()
            return ti >= cost and (
                ct.can_build_armoured_conveyor(pos, direction)
                or _would_destroy_clear(ct, pos)
            )
        case PlaceBridge(pos, target):
            cost, _ = ct.get_bridge_cost()
            return ti >= cost and (
                ct.can_build_bridge(pos, target) or _would_destroy_clear(ct, pos)
            )
        case PlaceRoad(pos):
            cost, _ = ct.get_road_cost()
            return ti >= cost and ct.can_build_road(pos)
        case PlaceFoundry(pos):
            cost, _ = ct.get_foundry_cost()
            return ti >= cost and (
                ct.can_build_foundry(pos) or _would_destroy_clear(ct, pos)
            )
        case PlaceSplitter(pos, direction):
            cost, _ = ct.get_splitter_cost()
            return ti >= cost and (
                ct.can_build_splitter(pos, direction) or _would_destroy_clear(ct, pos)
            )
        case PlaceBarrier(pos):
            cost, _ = ct.get_barrier_cost()
            return ti >= cost and (
                ct.can_build_barrier(pos) or _would_destroy_clear(ct, pos)
            )
        case PlaceSentinel(pos, direction):
            cost, _ = ct.get_sentinel_cost()
            return ti >= cost and (
                ct.can_build_sentinel(pos, direction) or _would_destroy_clear(ct, pos)
            )
        case PlaceLauncher(pos):
            cost, _ = ct.get_launcher_cost()
            return ti >= cost and (
                ct.can_build_launcher(pos) or _would_destroy_clear(ct, pos)
            )
        case PlaceGunner(pos, direction):
            cost, _ = ct.get_gunner_cost()
            return ti >= cost and (
                ct.can_build_gunner(pos, direction) or _would_destroy_clear(ct, pos)
            )
        case SelfDestruct() | Heal() | Fire():
            return True


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    bid = ct.get_tile_building_id(pos)
    if (
        bid is not None
        and ct.get_team(bid) == ct.get_team()
        and ct.get_entity_type(bid)
        in (
            EntityType.ROAD,
            EntityType.MARKER,
        )
    ):
        ct.destroy(pos)


def execute(action: Action, ct: Controller) -> None:
    match action:
        case PlaceHarvester(pos):
            _destroy_friendly(ct, pos)
            ct.build_harvester(pos)
        case PlaceConveyor(pos, direction):
            _destroy_friendly(ct, pos)
            ct.build_conveyor(pos, direction)
        case PlaceArmouredConveyor(pos, direction):
            _destroy_friendly(ct, pos)
            ct.build_armoured_conveyor(pos, direction)
        case PlaceBridge(pos, target):
            _destroy_friendly(ct, pos)
            ct.build_bridge(pos, target)
        case PlaceRoad(pos):
            ct.build_road(pos)
        case PlaceFoundry(pos):
            _destroy_friendly(ct, pos)
            ct.build_foundry(pos)
        case PlaceSplitter(pos, direction):
            _destroy_friendly(ct, pos)
            ct.build_splitter(pos, direction)
        case SelfDestruct():
            ct.self_destruct()
        case Heal(pos):
            ct.heal(pos)
        case PlaceBarrier(pos):
            _destroy_friendly(ct, pos)
            ct.build_barrier(pos)
        case PlaceSentinel(pos, direction):
            _destroy_friendly(ct, pos)
            ct.build_sentinel(pos, direction)
        case PlaceLauncher(pos):
            _destroy_friendly(ct, pos)
            ct.build_launcher(pos)
        case Fire():
            ct.fire(ct.get_position())
