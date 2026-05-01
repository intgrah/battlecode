from __future__ import annotations

from enum import Enum, auto

class Direction(Enum):
    North = auto()
    East = auto()
    South = auto()
    West = auto()

d = Direction.East
print("ok")
