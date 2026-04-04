from dataclasses import dataclass

from cambc import Direction, Position


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
