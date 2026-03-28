from __future__ import annotations

from builder.build import (
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
)
from cambc import Direction, Position
from util import Symmetry

from . import Build, Move, Opening, Step, Wait

_DIR_MIRROR_ROT: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.NORTHEAST: Direction.SOUTHWEST,
    Direction.EAST: Direction.WEST,
    Direction.SOUTHEAST: Direction.NORTHWEST,
    Direction.SOUTH: Direction.NORTH,
    Direction.SOUTHWEST: Direction.NORTHEAST,
    Direction.WEST: Direction.EAST,
    Direction.NORTHWEST: Direction.SOUTHEAST,
    Direction.CENTRE: Direction.CENTRE,
}

_DIR_MIRROR_HOR: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.NORTHEAST: Direction.SOUTHEAST,
    Direction.EAST: Direction.EAST,
    Direction.SOUTHEAST: Direction.NORTHEAST,
    Direction.SOUTH: Direction.NORTH,
    Direction.SOUTHWEST: Direction.NORTHWEST,
    Direction.WEST: Direction.WEST,
    Direction.NORTHWEST: Direction.SOUTHWEST,
    Direction.CENTRE: Direction.CENTRE,
}

_DIR_MIRROR_VER: dict[Direction, Direction] = {
    Direction.NORTH: Direction.NORTH,
    Direction.NORTHEAST: Direction.NORTHWEST,
    Direction.EAST: Direction.WEST,
    Direction.SOUTHEAST: Direction.SOUTHWEST,
    Direction.SOUTH: Direction.SOUTH,
    Direction.SOUTHWEST: Direction.SOUTHEAST,
    Direction.WEST: Direction.EAST,
    Direction.NORTHWEST: Direction.NORTHEAST,
    Direction.CENTRE: Direction.CENTRE,
}


def mirror_pos(p: Position, w: int, h: int, sym: Symmetry) -> Position:
    match sym:
        case Symmetry.ROT:
            return Position(w - 1 - p.x, h - 1 - p.y)
        case Symmetry.HOR:
            return Position(p.x, h - 1 - p.y)
        case Symmetry.VER:
            return Position(w - 1 - p.x, p.y)


def mirror_dir(d: Direction, sym: Symmetry) -> Direction:
    match sym:
        case Symmetry.ROT:
            return _DIR_MIRROR_ROT[d]
        case Symmetry.HOR:
            return _DIR_MIRROR_HOR[d]
        case Symmetry.VER:
            return _DIR_MIRROR_VER[d]


def mirror_offset(dx: int, dy: int, sym: Symmetry) -> tuple[int, int]:
    match sym:
        case Symmetry.ROT:
            return -dx, -dy
        case Symmetry.HOR:
            return dx, -dy
        case Symmetry.VER:
            return -dx, dy


def mirror_opening(opening: Opening, w: int, h: int, sym: Symmetry) -> Opening:
    def mp(p: Position) -> Position:
        return mirror_pos(p, w, h, sym)

    def md(d: Direction) -> Direction:
        return mirror_dir(d, sym)

    def mirror_action(a: object) -> object:
        match a:
            case PlaceRoad(pos):
                return PlaceRoad(mp(pos))
            case PlaceHarvester(pos):
                return PlaceHarvester(mp(pos))
            case PlaceConveyor(pos, direction):
                return PlaceConveyor(mp(pos), md(direction))
            case PlaceSplitter(pos, direction):
                return PlaceSplitter(mp(pos), md(direction))
            case PlaceBridge(pos, target):
                return PlaceBridge(mp(pos), mp(target))
            case PlaceBarrier(pos):
                return PlaceBarrier(mp(pos))
            case PlaceLauncher(pos):
                return PlaceLauncher(mp(pos))
            case PlaceGunner(pos, direction):
                return PlaceGunner(mp(pos), md(direction))
            case PlaceSentinel(pos, direction):
                return PlaceSentinel(mp(pos), md(direction))
            case PlaceFoundry(pos):
                return PlaceFoundry(mp(pos))
        return a

    def mirror_step(s: Step) -> Step:
        match s:
            case Move(direction=d):
                return Move(md(d))
            case Build(action=a):
                return Build(mirror_action(a))
            case Wait():
                return s
        return s

    mirrored_spawns = [
        mirror_offset(dx, dy, sym) if (dx, dy) is not None else None
        for dx, dy in opening.core_spawns
    ]
    mirrored_scripts = [
        [mirror_step(s) for s in script] for script in opening.builder_scripts
    ]
    return Opening(core_spawns=mirrored_spawns, builder_scripts=mirrored_scripts)
