from __future__ import annotations

from typing import Final

from cambc import Direction, Position

__all__ = [
    "DELTA_TO_DIR",
    "DIR4",
    "DIR8",
    "DIR8_DELTA",
    "get_direction_object",
]

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
