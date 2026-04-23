from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from typing import TYPE_CHECKING, NewType

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from bench_nav.common import Path_


AlgoName = NewType("AlgoName", str)


class Scenario(StrEnum):
    NO_ROADS = "no_roads"
    WITH_ROADS = "with_roads"


class CostUnit(Enum):
    HOPS = auto()
    COST = auto()


class Availability(Enum):
    STATIC = auto()
    FULL_MAP = auto()
    ONLINE = auto()


class Command(Enum):
    SPSP = auto()
    SSSP = auto()
    TABLE = auto()


@dataclass(frozen=True)
class Precomp[T]:
    label: str
    deps: frozenset[Precomp[object]]
    availability: Availability
    compute: Callable[[PrecompCtx], T]


@dataclass
class PrecompCtx:
    w: int
    h: int
    n: int
    _values: dict[Precomp[object], object] = field(default_factory=dict)

    def __getitem__[T](self, p: Precomp[T]) -> T:
        return self._values[p]  # type: ignore[return-value]

    def put[T](self, p: Precomp[T], v: T) -> None:
        self._values[p] = v

    def has(self, p: Precomp[object]) -> bool:
        return p in self._values


@dataclass(frozen=True)
class SensorReading:
    newly_visible: tuple[int, ...]
    cost: Mapping[int, int]


@dataclass(frozen=True)
class SsspAlgo:
    name: AlgoName
    requires: frozenset[Precomp[object]]
    unit: CostUnit
    solve: Callable[[PrecompCtx, int], list[int]]


@dataclass(frozen=True)
class SequentialSpspAlgo[S]:
    name: AlgoName
    requires: frozenset[Precomp[object]]
    init: Callable[[PrecompCtx, SensorReading, int, int], tuple[S, Path_]]
    step: Callable[[S, SensorReading, int, int], tuple[S, Path_]]


@dataclass(frozen=True)
class SequentialQuery:
    start: int
    goals: tuple[int, ...]
    vision_r2: int


@dataclass(frozen=True)
class SsspQuery:
    start: int


@dataclass(frozen=True)
class Walk:
    final_pos: int
    cost_walked: int
    steps_taken: int
    tiles_revealed: int
    reached_all: bool
    step_times_us: tuple[float, ...]


@dataclass(frozen=True)
class SpspResult:
    reached: bool
    opt_ratio: float | None
    first_move_correct: bool | None
    total_time_us: float
    walk: Walk


@dataclass(frozen=True)
class SsspResult:
    worst_ratio: float
    exact: bool
    time_us: float
