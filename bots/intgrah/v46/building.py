from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Direction, Position, Team


@dataclass(frozen=True, slots=True)
class BuildingCore:
    team: Team


@dataclass(frozen=True, slots=True)
class BuildingHarvester:
    team: Team


@dataclass(frozen=True, slots=True)
class BuildingConveyor:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingArmouredConveyor:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingSplitter:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingBridge:
    team: Team
    target: Position


@dataclass(frozen=True, slots=True)
class BuildingFoundry:
    team: Team


@dataclass(frozen=True, slots=True)
class BuildingBarrier:
    team: Team


@dataclass(frozen=True, slots=True)
class BuildingRoad:
    team: Team


@dataclass(frozen=True, slots=True)
class BuildingMarker:
    team: Team
    value: int


@dataclass(frozen=True, slots=True)
class BuildingGunner:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingSentinel:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingBreach:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class BuildingLauncher:
    team: Team


type Building = (
    BuildingCore
    | BuildingHarvester
    | BuildingConveyor
    | BuildingArmouredConveyor
    | BuildingSplitter
    | BuildingBridge
    | BuildingFoundry
    | BuildingBarrier
    | BuildingRoad
    | BuildingMarker
    | BuildingGunner
    | BuildingSentinel
    | BuildingBreach
    | BuildingLauncher
)
