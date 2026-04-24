from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from typing import TYPE_CHECKING, ClassVar, NewType, cast, override

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from bench_nav.common import Path_


AlgoName = NewType("AlgoName", str)

_CATEGORY_MARKERS = frozenset({"sssp", "spsp", "mpsp", "online"})


def _derive_algo_name(module: str) -> AlgoName | None:
    parts = module.split(".")
    markers = [i for i, p in enumerate(parts) if p in _CATEGORY_MARKERS]
    if not markers:
        return None
    tail = parts[markers[-1] + 1 :]
    if len(tail) >= 2:
        folder, leaf = tail[-2], tail[-1]
        if leaf == folder:
            tail = tail[:-1]
        elif leaf.startswith(f"{folder}_"):
            tail = [*tail[:-1], leaf[len(folder) + 1 :]]
    return AlgoName("-".join(p.replace("_", "-") for p in tail))


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
    MPSP = auto()
    ONLINE = auto()
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
        return cast("T", self._values[p])

    def put[T](self, p: Precomp[T], v: T) -> None:
        self._values[p] = v

    def has(self, p: Precomp[object]) -> bool:
        return p in self._values


@dataclass(frozen=True)
class SensorReading:
    newly_visible: tuple[int, ...]
    cost: Mapping[int, int]


class _AutoName(ABC):
    NAME: ClassVar[AlgoName]

    @override
    def __init_subclass__(cls, **kw: object) -> None:
        super().__init_subclass__(**kw)
        if "NAME" not in cls.__dict__:
            derived = _derive_algo_name(cls.__module__)
            if derived is not None:
                cls.NAME = derived


class Spsp(_AutoName):
    """Single-pair pathfinder. Offline, one-shot per query: plan(start, goal)
    produces a full path and no useful cross-query state."""

    REQUIRES: ClassVar[frozenset[Precomp[object]]]

    @abstractmethod
    def __init__(self, ctx: PrecompCtx) -> None: ...

    @abstractmethod
    def plan(self, start: int, goal: int) -> Path_: ...


class Mpsp(_AutoName):
    """Multi-pair pathfinder. Offline, but the algorithm incrementally builds
    up precomputation across multiple (start, goal) queries — precomp made
    during one plan() call benefits future plan() calls to different goals.
    Same surface as Spsp; distinct type to mark the different contract."""

    REQUIRES: ClassVar[frozenset[Precomp[object]]]

    @abstractmethod
    def __init__(self, ctx: PrecompCtx) -> None: ...

    @abstractmethod
    def plan(self, start: int, goal: int) -> Path_: ...


class Sssp(_AutoName):
    """A single-source solver. Built once per (map, scenario); each solve(start)
    returns the full dist array from that source."""

    REQUIRES: ClassVar[frozenset[Precomp[object]]]
    UNIT: ClassVar[CostUnit]

    @abstractmethod
    def __init__(self, ctx: PrecompCtx) -> None: ...

    @abstractmethod
    def solve(self, start: int) -> list[int]: ...


class Online(_AutoName):
    """An online pathfinder. Built once at journey start with (w, h); at every
    turn step(reading, pos, goal) is called with a sensor delta and returns the
    next tile to move to. Maintains self state across turns (belief map,
    incrementally-patched precomputation, wall-following memory). Does NOT
    have access to the full cost grid at build time — discovers the map from
    sensor readings as it moves."""

    @abstractmethod
    def __init__(self, w: int, h: int) -> None: ...

    @abstractmethod
    def step(self, reading: SensorReading, pos: int, goal: int) -> int | None: ...


@dataclass(frozen=True)
class SequentialQuery:
    start: int
    goals: tuple[int, ...]


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
    ref_reachable: bool
    opt_ratio: float | None
    first_move_correct: bool | None
    total_time_us: float
    walk: Walk


@dataclass(frozen=True)
class SsspResult:
    worst_ratio: float
    exact: bool
    time_us: float
