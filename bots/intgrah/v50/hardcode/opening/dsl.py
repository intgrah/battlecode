from __future__ import annotations

__all__ = [
    "NE",
    "NW",
    "SE",
    "SW",
    "DslTurn",
    "E",
    "N",
    "S",
    "W",
    "ba",
    "br",
    "c",
    "f",
    "gn",
    "h",
    "ln",
    "rd",
    "sn",
    "sp",
    "wait",
]

from dataclasses import dataclass

from cambc import Direction


@dataclass(frozen=True, slots=True)
class DslPlaceHarvester:
    direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceConveyor:
    direction: Direction
    building_direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceArmouredConveyor:
    direction: Direction
    building_direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceBridge:
    direction: Direction
    target_vector: tuple[int, int]


@dataclass(frozen=True, slots=True)
class DslPlaceRoad:
    direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceFoundry:
    direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceSplitter:
    direction: Direction
    building_direction: Direction


@dataclass(frozen=True, slots=True)
class DslSelfDestruct:
    pass


@dataclass(frozen=True, slots=True)
class DslHeal:
    direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceBarrier:
    direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceSentinel:
    direction: Direction
    building_direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceLauncher:
    direction: Direction


@dataclass(frozen=True, slots=True)
class DslPlaceGunner:
    direction: Direction
    building_direction: Direction


class DslFire:
    pass


type DslAction = (
    DslPlaceHarvester
    | DslPlaceConveyor
    | DslPlaceArmouredConveyor
    | DslPlaceBridge
    | DslPlaceRoad
    | DslPlaceFoundry
    | DslPlaceSplitter
    | DslSelfDestruct
    | DslHeal
    | DslPlaceBarrier
    | DslPlaceSentinel
    | DslPlaceLauncher
    | DslPlaceGunner
    | DslFire
)


@dataclass(frozen=True, slots=True)
class DslActionOnly:
    action: DslAction

    def __or__(self, move: DslMoveOnly) -> DslActionMove:
        return DslActionMove(self.action, move.move)


@dataclass(frozen=True, slots=True)
class DslMoveOnly:
    move: Direction

    def __or__(self, act: DslActionOnly) -> DslMoveAction:
        return DslMoveAction(self.move, act.action)

    def rd(self) -> DslActionMove:
        return DslActionMove(DslPlaceRoad(self.move), self.move)


@dataclass(frozen=True, slots=True)
class DslActionMove:
    action: DslAction
    move: Direction


@dataclass(frozen=True, slots=True)
class DslMoveAction:
    move: Direction
    action: DslAction


@dataclass(frozen=True, slots=True)
class DslWait:
    pass


type DslTurn = DslWait | DslActionOnly | DslMoveOnly | DslActionMove | DslMoveAction


N = DslMoveOnly(Direction.NORTH)
NE = DslMoveOnly(Direction.NORTHEAST)
E = DslMoveOnly(Direction.EAST)
SE = DslMoveOnly(Direction.SOUTHEAST)
S = DslMoveOnly(Direction.SOUTH)
SW = DslMoveOnly(Direction.SOUTHWEST)
W = DslMoveOnly(Direction.WEST)
NW = DslMoveOnly(Direction.NORTHWEST)

wait = DslWait()


def rd(d: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceRoad(d.move))


def h(d: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceHarvester(d.move))


def ba(d: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceBarrier(d.move))


def br(d: DslMoveOnly, tv: tuple[int, int]) -> DslActionOnly:
    return DslActionOnly(DslPlaceBridge(d.move, tv))


def c(d: DslMoveOnly, facing: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceConveyor(d.move, facing.move))


def sp(d: DslMoveOnly, facing: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceSplitter(d.move, facing.move))


def sn(d: DslMoveOnly, facing: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceSentinel(d.move, facing.move))


def gn(d: DslMoveOnly, facing: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceGunner(d.move, facing.move))


def ln(d: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceLauncher(d.move))


def f(d: DslMoveOnly) -> DslActionOnly:
    return DslActionOnly(DslPlaceFoundry(d.move))
