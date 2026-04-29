from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cambc import Position

__all__ = [
    "chebyshev",
    "claims_by_proximity",
    "closest",
    "manhattan",
    "reachable_path_end",
]


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


def claims_by_proximity(
    my_pos: Position,
    my_id: int,
    target: Position,
    friendlies: Iterable[tuple[Position, int]],
) -> bool:
    """Return True iff `my_id` at `my_pos` is the rightful claimant of
    `target` over all `friendlies`.

    The claim is decided by Chebyshev distance to `target`, with builder id
    as deterministic tiebreak (smaller id wins). Used by tasks that scan
    candidate targets (ore tiles, dangling ends, heal targets) and want
    exactly one builder per target without inter-builder messaging — every
    builder runs the same comparison from its own perspective and only the
    rightful claimant returns True.

    `friendlies` is an iterable of `(position, id)` pairs of OTHER friendly
    builders (do not include `my_pos`/`my_id`). Returns False if any
    friendly is strictly closer (Chebyshev) or tied with a smaller id.
    """
    my_d = chebyshev(my_pos, target)
    for fb_pos, fb_id in friendlies:
        fb_d = chebyshev(fb_pos, target)
        if fb_d < my_d or (fb_d == my_d and fb_id < my_id):
            return False
    return True
