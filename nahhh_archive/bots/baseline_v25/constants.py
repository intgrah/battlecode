"""Shared constants for the tree_denial_clean bot."""

from __future__ import annotations

import os
import sys

from cambc import Direction, EntityType

DEBUG = os.environ.get("CAMBC_DEBUG", "").strip().lower() not in {"", "0", "false", "no"}

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

ALL_DIRECTIONS = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]

DIRECTION_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (0, -1),
    Direction.NORTHEAST: (1, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTHEAST: (1, 1),
    Direction.SOUTH: (0, 1),
    Direction.SOUTHWEST: (-1, 1),
    Direction.WEST: (-1, 0),
    Direction.NORTHWEST: (-1, -1),
}

DELTA_TO_DIRECTION: dict[tuple[int, int], Direction] = {
    v: k for k, v in DIRECTION_DELTA.items()
}

WALKABLE_BUILDINGS = {
    EntityType.ROAD,
    EntityType.CONVEYOR,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.SPLITTER,
    EntityType.BRIDGE,
}

BRIDGE_MAX_DIST_SQ = 9

# Sector-based exploration
SECTOR_CLAIM_TTL = 100
SECTOR_OFFSETS = [(1, -1), (1, 1), (-1, 1), (-1, -1)]  # NE, SE, SW, NW unit vectors

# 90-degree cardinal rotations (left = counter-clockwise, right = clockwise).
CARDINAL_LEFT: dict[Direction, Direction] = {
    Direction.NORTH: Direction.WEST,
    Direction.WEST: Direction.SOUTH,
    Direction.SOUTH: Direction.EAST,
    Direction.EAST: Direction.NORTH,
}
CARDINAL_RIGHT: dict[Direction, Direction] = {v: k for k, v in CARDINAL_LEFT.items()}


def dbg(*parts) -> None:
    if DEBUG:
        print(*parts)
        print(*parts, file=sys.stderr)
