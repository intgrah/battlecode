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
class DslActionMove:
    action: DslAction | None
    move: Direction | None


@dataclass(frozen=True, slots=True)
class DslMoveAction:
    move: Direction | None
    action: DslAction | None


type DslTurn = DslMoveAction | DslActionMove


class Mov:
    """Wrapper for composing direction | action into DslMoveAction."""

    __slots__ = ("dir",)

    def __init__(self, d: Direction) -> None:
        self.dir = d

    def __or__(self, act: Act) -> DslMoveAction:
        return DslMoveAction(self.dir, act.action)

    def rd(self) -> DslActionMove:
        return DslActionMove(DslPlaceRoad(self.dir), self.dir)

    def turn(self) -> DslActionMove:
        return DslActionMove(None, self.dir)


class Act:
    """Wrapper for composing action | direction into DslActionMove."""

    __slots__ = ("action",)

    def __init__(self, action: DslAction) -> None:
        self.action = action

    def __or__(self, move: Mov | Direction | None) -> DslActionMove:
        if isinstance(move, Mov):
            return DslActionMove(self.action, move.dir)
        return DslActionMove(self.action, move)

    def turn(self) -> DslActionMove:
        return DslActionMove(self.action, None)


N = Mov(Direction.NORTH)
NE = Mov(Direction.NORTHEAST)
E = Mov(Direction.EAST)
SE = Mov(Direction.SOUTHEAST)
S = Mov(Direction.SOUTH)
SW = Mov(Direction.SOUTHWEST)
W = Mov(Direction.WEST)
NW = Mov(Direction.NORTHWEST)

wait = DslActionMove(None, None)


def rd(d: Mov) -> Act:
    return Act(DslPlaceRoad(d.dir))


def h(d: Mov) -> Act:
    return Act(DslPlaceHarvester(d.dir))


def ba(d: Mov) -> Act:
    return Act(DslPlaceBarrier(d.dir))


def br(d: Mov, tv: tuple[int, int]) -> Act:
    return Act(DslPlaceBridge(d.dir, tv))


def c(d: Mov, facing: Mov) -> Act:
    return Act(DslPlaceConveyor(d.dir, facing.dir))


def sp(d: Mov, facing: Mov) -> Act:
    return Act(DslPlaceSplitter(d.dir, facing.dir))


def sn(d: Mov, facing: Mov) -> Act:
    return Act(DslPlaceSentinel(d.dir, facing.dir))


def gn(d: Mov, facing: Mov) -> Act:
    return Act(DslPlaceGunner(d.dir, facing.dir))


def ln(d: Mov) -> Act:
    return Act(DslPlaceLauncher(d.dir))


def f(d: Mov) -> Act:
    return Act(DslPlaceFoundry(d.dir))
