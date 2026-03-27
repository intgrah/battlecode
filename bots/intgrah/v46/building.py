from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Direction, Position, Team


@dataclass(frozen=True, slots=True)
class Core:
    team: Team


@dataclass(frozen=True, slots=True)
class Harvester:
    team: Team


@dataclass(frozen=True, slots=True)
class Conveyor:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class ArmouredConveyor:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class Splitter:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class Bridge:
    team: Team
    target: Position


@dataclass(frozen=True, slots=True)
class Foundry:
    team: Team


@dataclass(frozen=True, slots=True)
class Barrier:
    team: Team


@dataclass(frozen=True, slots=True)
class Road:
    team: Team


@dataclass(frozen=True, slots=True)
class Marker:
    team: Team
    value: int


@dataclass(frozen=True, slots=True)
class Gunner:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class Sentinel:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class Breach:
    team: Team
    direction: Direction


@dataclass(frozen=True, slots=True)
class Launcher:
    team: Team


type Building = (
    Core
    | Harvester
    | Conveyor
    | ArmouredConveyor
    | Splitter
    | Bridge
    | Foundry
    | Barrier
    | Road
    | Marker
    | Gunner
    | Sentinel
    | Breach
    | Launcher
)
