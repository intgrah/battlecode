"""Translation of `bots/intgrah/v54.7.9/util/directions.py`."""

from __future__ import annotations

from typing import Final

from cambc import Direction

DIR8: Final[list[Direction]] = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
"""
`N, NE, E, SE, S, SW, W, NW` — the eight non-CENTRE directions, in
`EntityType` enum order (matches Python `[d for d in Direction if d != CENTRE]`).
"""
DIR4: Final[list[Direction]] = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]
"""Cardinal directions only: `N, E, S, W`."""


def is_cardinal(d):
    """
    True for the four cardinal directions (N/E/S/W). Mirrors the Rust
    `Direction::is_cardinal()` helper from `libre-engine`, which has no
    Python counterpart on `cambc.Direction`.
    """
    return d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


DIR8_DELTA: Final[list[tuple[int, int]]] = [
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
]
"""`(dx, dy)` offsets for `DIR8`, in the same order."""


def delta_to_dir(dx, dy):
    """
    Convert a magnitude-1 or sqrt-2 vector to its `Direction`. Returns `None`
    for any other delta (including `(0, 0)` and longer vectors).
    """
    match (dx, dy):
        case (0, -1):
            return Direction.NORTH
        case (1, -1):
            return Direction.NORTHEAST
        case (1, 0):
            return Direction.EAST
        case (1, 1):
            return Direction.SOUTHEAST
        case (0, 1):
            return Direction.SOUTH
        case (-1, 1):
            return Direction.SOUTHWEST
        case (-1, 0):
            return Direction.WEST
        case (-1, -1):
            return Direction.NORTHWEST
        case _:
            return None


def get_direction_object(from_pos, to_pos):
    """Direction from `from_pos` to `to_pos`, or `None` if not adjacent in king-move."""
    return delta_to_dir(to_pos.x - from_pos.x, to_pos.y - from_pos.y)
