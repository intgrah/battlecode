"""Build action dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, Direction, Position


@dataclass(frozen=True, slots=True)
class PlaceRoad:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceConveyor:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceSplitter:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceBridge:
    pos: Position
    target: Position


@dataclass(frozen=True, slots=True)
class PlaceHarvester:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceFoundry:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceBarrier:
    pos: Position


@dataclass(frozen=True, slots=True)
class PlaceGunner:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceSentinel:
    pos: Position
    direction: Direction


@dataclass(frozen=True, slots=True)
class PlaceLauncher:
    pos: Position


@dataclass(frozen=True, slots=True)
class Heal:
    pos: Position


@dataclass(frozen=True, slots=True)
class Fire:
    pos: Position


type Action = (
    PlaceRoad
    | PlaceConveyor
    | PlaceSplitter
    | PlaceBridge
    | PlaceHarvester
    | PlaceFoundry
    | PlaceBarrier
    | PlaceGunner
    | PlaceSentinel
    | PlaceLauncher
    | Heal
    | Fire
)


def destroy_friendly(ct: Controller, pos: Position) -> None:
    """Destroy allied building at pos if present."""
    bid = ct.get_tile_building_id(pos)
    if bid is not None and ct.get_team(bid) == ct.get_team() and ct.can_destroy(pos):
        ct.destroy(pos)


def execute(action: Action, ct: Controller) -> None:
    """Execute a build action, destroying friendly buildings if needed."""
    match action:
        case PlaceRoad(pos):
            destroy_friendly(ct, pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
        case PlaceConveyor(pos, direction):
            destroy_friendly(ct, pos)
            if ct.can_build_conveyor(pos, direction):
                ct.build_conveyor(pos, direction)
        case PlaceSplitter(pos, direction):
            destroy_friendly(ct, pos)
            if ct.can_build_splitter(pos, direction):
                ct.build_splitter(pos, direction)
        case PlaceBridge(pos, target):
            destroy_friendly(ct, pos)
            if ct.can_build_bridge(pos, target):
                ct.build_bridge(pos, target)
        case PlaceHarvester(pos):
            destroy_friendly(ct, pos)
            if ct.can_build_harvester(pos):
                ct.build_harvester(pos)
        case PlaceFoundry(pos):
            destroy_friendly(ct, pos)
            if ct.can_build_foundry(pos):
                ct.build_foundry(pos)
        case PlaceBarrier(pos):
            destroy_friendly(ct, pos)
            if ct.can_build_barrier(pos):
                ct.build_barrier(pos)
        case PlaceGunner(pos, direction):
            destroy_friendly(ct, pos)
            if ct.can_build_gunner(pos, direction):
                ct.build_gunner(pos, direction)
        case PlaceSentinel(pos, direction):
            destroy_friendly(ct, pos)
            if ct.can_build_sentinel(pos, direction):
                ct.build_sentinel(pos, direction)
        case PlaceLauncher(pos):
            destroy_friendly(ct, pos)
            if ct.can_build_launcher(pos):
                ct.build_launcher(pos)
        case Heal(pos):
            if ct.can_heal(pos):
                ct.heal(pos)
        case Fire(pos):
            if ct.can_fire(pos):
                ct.fire(pos)
