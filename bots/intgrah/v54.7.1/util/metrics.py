from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cambc import Position

__all__ = ["chebyshev", "closest", "manhattan", "reachable_path_end"]


def manhattan(pos1: Position, pos2: Position) -> int:
    """L-1 distance."""
    return abs(pos1.x - pos2.x) + abs(pos1.y - pos2.y)


def euclidean_sq(pos1: Position, pos2: Position) -> int:
    """L-2 distance, squared."""
    return abs(pos1.x - pos2.x) ** 2 + abs(pos1.y - pos2.y) ** 2


def chebyshev(pos1: Position, pos2: Position) -> int:
    """L-infinity distance."""
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


def closest(target: Position, positions: Iterable[Position]) -> Position | None:
    return min(positions, key=target.distance_squared, default=None)
