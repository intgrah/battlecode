"""Mirror DSL scripts for team B based on map symmetry.

Transforms DslTurn sequences so that relative directions are flipped.
The compiler then resolves them to correct absolute positions using
team B's core position.
"""

__all__ = ["mirror_opening", "mirror_script", "mirror_spawns"]

from cambc import Direction
from util import Symmetry

from . import Opening
from .dsl import (
    DslAction,
    DslActionMove,
    DslFire,
    DslHeal,
    DslMoveAction,
    DslPlaceArmouredConveyor,
    DslPlaceBarrier,
    DslPlaceBridge,
    DslPlaceConveyor,
    DslPlaceFoundry,
    DslPlaceGunner,
    DslPlaceHarvester,
    DslPlaceLauncher,
    DslPlaceRoad,
    DslPlaceSentinel,
    DslPlaceSplitter,
    DslSelfDestruct,
    DslTurn,
)

_DIR_MIRROR: dict[Symmetry, dict[Direction, Direction]] = {
    Symmetry.ROT: {
        Direction.NORTH: Direction.SOUTH,
        Direction.NORTHEAST: Direction.SOUTHWEST,
        Direction.EAST: Direction.WEST,
        Direction.SOUTHEAST: Direction.NORTHWEST,
        Direction.SOUTH: Direction.NORTH,
        Direction.SOUTHWEST: Direction.NORTHEAST,
        Direction.WEST: Direction.EAST,
        Direction.NORTHWEST: Direction.SOUTHEAST,
        Direction.CENTRE: Direction.CENTRE,
    },
    Symmetry.HOR: {
        Direction.NORTH: Direction.SOUTH,
        Direction.NORTHEAST: Direction.SOUTHEAST,
        Direction.EAST: Direction.EAST,
        Direction.SOUTHEAST: Direction.NORTHEAST,
        Direction.SOUTH: Direction.NORTH,
        Direction.SOUTHWEST: Direction.NORTHWEST,
        Direction.WEST: Direction.WEST,
        Direction.NORTHWEST: Direction.SOUTHWEST,
        Direction.CENTRE: Direction.CENTRE,
    },
    Symmetry.VER: {
        Direction.NORTH: Direction.NORTH,
        Direction.NORTHEAST: Direction.NORTHWEST,
        Direction.EAST: Direction.WEST,
        Direction.SOUTHEAST: Direction.SOUTHWEST,
        Direction.SOUTH: Direction.SOUTH,
        Direction.SOUTHWEST: Direction.SOUTHEAST,
        Direction.WEST: Direction.EAST,
        Direction.NORTHWEST: Direction.NORTHEAST,
        Direction.CENTRE: Direction.CENTRE,
    },
}


def _md(d: Direction, sym: Symmetry) -> Direction:
    return _DIR_MIRROR[sym][d]


def _mv(v: tuple[int, int], sym: Symmetry) -> tuple[int, int]:
    dx, dy = v
    match sym:
        case Symmetry.ROT:
            return -dx, -dy
        case Symmetry.HOR:
            return dx, -dy
        case Symmetry.VER:
            return -dx, dy


def _mirror_action(a: DslAction, sym: Symmetry) -> DslAction:
    match a:
        case DslPlaceRoad(d):
            return DslPlaceRoad(_md(d, sym))
        case DslPlaceHarvester(d):
            return DslPlaceHarvester(_md(d, sym))
        case DslPlaceConveyor(d, bd):
            return DslPlaceConveyor(_md(d, sym), _md(bd, sym))
        case DslPlaceArmouredConveyor(d, bd):
            return DslPlaceArmouredConveyor(_md(d, sym), _md(bd, sym))
        case DslPlaceBridge(d, tv):
            return DslPlaceBridge(_md(d, sym), _mv(tv, sym))
        case DslPlaceFoundry(d):
            return DslPlaceFoundry(_md(d, sym))
        case DslPlaceSplitter(d, bd):
            return DslPlaceSplitter(_md(d, sym), _md(bd, sym))
        case DslPlaceBarrier(d):
            return DslPlaceBarrier(_md(d, sym))
        case DslPlaceSentinel(d, bd):
            return DslPlaceSentinel(_md(d, sym), _md(bd, sym))
        case DslPlaceLauncher(d):
            return DslPlaceLauncher(_md(d, sym))
        case DslPlaceGunner(d, bd):
            return DslPlaceGunner(_md(d, sym), _md(bd, sym))
        case DslHeal(d):
            return DslHeal(_md(d, sym))
        case DslSelfDestruct() | DslFire():
            return a


def _mirror_turn(turn: DslTurn, sym: Symmetry) -> DslTurn:
    match turn:
        case DslActionMove(action, move):
            return DslActionMove(
                _mirror_action(action, sym) if action is not None else None,
                _md(move, sym) if move is not None else None,
            )
        case DslMoveAction(move, action):
            return DslMoveAction(
                _md(move, sym) if move is not None else None,
                _mirror_action(action, sym) if action is not None else None,
            )


def mirror_script(script: list[DslTurn], sym: Symmetry) -> list[DslTurn]:
    return [_mirror_turn(t, sym) for t in script]


def mirror_spawns(
    spawns: list[tuple[int, int] | None],
    sym: Symmetry,
) -> list[tuple[int, int] | None]:
    return [_mv(s, sym) if s is not None else None for s in spawns]


def mirror_opening(opening: Opening, sym: Symmetry) -> Opening:
    return Opening(
        core_spawns=mirror_spawns(opening.core_spawns, sym),
        builder_scripts=[mirror_script(s, sym) for s in opening.builder_scripts],
    )
