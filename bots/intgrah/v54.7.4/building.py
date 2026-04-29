from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cambc import Controller, EntityType

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


@dataclass(frozen=True, slots=True)
class BuildingMarker:
    team: Team
    value: int


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
    | BuildingGunner
    | BuildingSentinel
    | BuildingBreach
    | BuildingLauncher
    | BuildingMarker
)


def make_building(ct: Controller, bid: int) -> Building:
    team = ct.get_team(bid)
    match ct.get_entity_type(bid):
        case EntityType.CONVEYOR:
            return BuildingConveyor(team, ct.get_direction(bid))
        case EntityType.ARMOURED_CONVEYOR:
            return BuildingArmouredConveyor(team, ct.get_direction(bid))
        case EntityType.SPLITTER:
            return BuildingSplitter(team, ct.get_direction(bid))
        case EntityType.GUNNER:
            return BuildingGunner(team, ct.get_direction(bid))
        case EntityType.SENTINEL:
            return BuildingSentinel(team, ct.get_direction(bid))
        case EntityType.BREACH:
            return BuildingBreach(team, ct.get_direction(bid))
        case EntityType.BRIDGE:
            return BuildingBridge(team, ct.get_bridge_target(bid))
        case EntityType.CORE:
            return BuildingCore(team)
        case EntityType.HARVESTER:
            return BuildingHarvester(team)
        case EntityType.FOUNDRY:
            return BuildingFoundry(team)
        case EntityType.BARRIER:
            return BuildingBarrier(team)
        case EntityType.ROAD:
            return BuildingRoad(team)
        case EntityType.LAUNCHER:
            return BuildingLauncher(team)
        case EntityType.MARKER:
            return BuildingMarker(team, ct.get_marker_value(bid) if team == ct.get_team() else 0)
        case EntityType.BUILDER_BOT:
            msg = "BUILDER_BOT is not a building"
            raise ValueError(msg)
