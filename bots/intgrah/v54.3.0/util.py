from __future__ import annotations

from contextlib import AbstractContextManager
from enum import StrEnum
from time import perf_counter_ns
from typing import TYPE_CHECKING, ClassVar, Final, Self, override

from cambc import Direction, EntityType, GameConstants, Position

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import TracebackType


class Timer(AbstractContextManager):
    """Context manager-based timing.
    Nested contexts result in indentation.
    """

    _depth: ClassVar[int] = 0
    """Global variable representing depth. Not thread safe."""

    t0: int
    """Start time."""
    t1: int
    """End time."""

    def __init__(self, name: str) -> None:
        self.name = name

    @override
    def __enter__(self) -> Self:
        Timer._depth += 1
        self.t0 = perf_counter_ns()
        return self

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        Timer._depth -= 1
        indent = "  " * Timer._depth
        self.t1 = perf_counter_ns()
        dt = self.t1 - self.t0
        print(f"{indent}{self.name}={dt // 1000}us")


class Symmetry(StrEnum):
    """All maps exhibit one of these symmetries."""

    ROT = "rot"
    """Rotational symmetry. x and y are flipped."""
    HOR = "hor"
    """Horizontal symmetry. x is unchanged, y is flipped."""
    VER = "ver"
    """Vertical symmetry. x is flipped, y is unchanged."""


INF: Final = 1_000_000
"""Large number used to represent unreachable distances or hard preferences."""

ROAD_COST: Final = 3
"""The cost of having to place a road on an empty tile, used for A* navigation."""

W: Final = 50
"""Hardcoded map-size stride for flat indexing. All flat arrays are length N."""
N: Final = W * W
"""Length of all flat per-tile arrays (2500)."""

DIR8: Final = [d for d in Direction if d != Direction.CENTRE]
"""N, NE, E, SE, S, SW, W, NW."""

DIR4: Final = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]
"""N, E, S, W"""

DIR8_DELTA: Final = [c.delta() for c in DIR8]
"""Vectors of those directions in `DIR8`."""

DELTA_TO_DIR: Final = {
    (1, 0): Direction.EAST,
    (-1, 0): Direction.WEST,
    (0, 1): Direction.SOUTH,
    (0, -1): Direction.NORTH,
    (1, 1): Direction.SOUTHEAST,
    (1, -1): Direction.NORTHEAST,
    (-1, 1): Direction.SOUTHWEST,
    (-1, -1): Direction.NORTHWEST,
}
"""Convert a magnitude 1 or sqrt 2 vector to its `Direction`."""


def get_direction_object(from_pos: Position, to_pos: Position) -> Direction | None:
    return DELTA_TO_DIR.get((to_pos.x - from_pos.x, to_pos.y - from_pos.y))


def manhattan(pos1: Position, pos2: Position) -> int:
    """L-1 norm."""
    return abs(pos1.x - pos2.x) + abs(pos1.y - pos2.y)


def chebyshev(pos1: Position, pos2: Position) -> int:
    """L-infinity norm."""
    return max(abs(pos1.x - pos2.x), abs(pos1.y - pos2.y))


def reachable_path_end(
    path: list[Position],
    current_pos: Position,
    max_range: int,
) -> Position:
    for pos in reversed(path):
        if current_pos.distance_squared(pos) <= max_range**2:
            return pos
    return current_pos


BASE_COST: Final = {
    EntityType.BUILDER_BOT: GameConstants.BUILDER_BOT_BASE_COST,
    EntityType.HARVESTER: GameConstants.HARVESTER_BASE_COST,
    EntityType.SENTINEL: GameConstants.SENTINEL_BASE_COST,
    EntityType.GUNNER: GameConstants.GUNNER_BASE_COST,
    EntityType.LAUNCHER: GameConstants.LAUNCHER_BASE_COST,
    EntityType.CONVEYOR: GameConstants.CONVEYOR_BASE_COST,
    EntityType.BRIDGE: GameConstants.BRIDGE_BASE_COST,
    EntityType.SPLITTER: GameConstants.SPLITTER_BASE_COST,
    EntityType.BARRIER: GameConstants.BARRIER_BASE_COST,
}


def closest(target: Position, positions: Iterable[Position]) -> Position | None:
    return min(positions, key=target.distance_squared, default=None)
