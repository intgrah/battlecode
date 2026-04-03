"""Building dataclasses — lightweight representations of buildings on the map."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cambc import EntityType

if TYPE_CHECKING:
    from cambc import Direction


@dataclass(frozen=True, slots=True)
class BuildingRoad:
    team: object


@dataclass(frozen=True, slots=True)
class BuildingConveyor:
    team: object
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingArmouredConveyor:
    team: object
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingSplitter:
    team: object
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingBridge:
    team: object
    target: tuple[int, int]


@dataclass(frozen=True, slots=True)
class BuildingHarvester:
    team: object


@dataclass(frozen=True, slots=True)
class BuildingFoundry:
    team: object


@dataclass(frozen=True, slots=True)
class BuildingBarrier:
    team: object


@dataclass(frozen=True, slots=True)
class BuildingCore:
    team: object


@dataclass(frozen=True, slots=True)
class BuildingMarker:
    team: object
    value: int = 0


@dataclass(frozen=True, slots=True)
class BuildingGunner:
    team: object
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingSentinel:
    team: object
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingBreach:
    team: object
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingLauncher:
    team: object


type Building = (
    BuildingRoad
    | BuildingConveyor
    | BuildingArmouredConveyor
    | BuildingSplitter
    | BuildingBridge
    | BuildingHarvester
    | BuildingFoundry
    | BuildingBarrier
    | BuildingCore
    | BuildingMarker
    | BuildingGunner
    | BuildingSentinel
    | BuildingBreach
    | BuildingLauncher
)


ETYPE_BUILDING: dict[EntityType, type] = {
    EntityType.ROAD: BuildingRoad,
    EntityType.CONVEYOR: BuildingConveyor,
    EntityType.ARMOURED_CONVEYOR: BuildingArmouredConveyor,
    EntityType.SPLITTER: BuildingSplitter,
    EntityType.BRIDGE: BuildingBridge,
    EntityType.HARVESTER: BuildingHarvester,
    EntityType.FOUNDRY: BuildingFoundry,
    EntityType.BARRIER: BuildingBarrier,
    EntityType.CORE: BuildingCore,
    EntityType.MARKER: BuildingMarker,
    EntityType.GUNNER: BuildingGunner,
    EntityType.SENTINEL: BuildingSentinel,
    EntityType.BREACH: BuildingBreach,
    EntityType.LAUNCHER: BuildingLauncher,
}
