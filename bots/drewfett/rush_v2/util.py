"""Shared constants, directions, deltas."""

from __future__ import annotations

from enum import IntEnum
from typing import Final

from cambc import Direction

# -- Pathfinding costs --
INF: Final[int] = 1_000_000
COST_ROAD: Final[int] = 1
COST_EMPTY: Final[int] = 3
COST_UNSEEN: Final[int] = 3
COST_IMPASSABLE: Final[int] = INF
COST_DANGER: Final[int] = 5
COST_FLOW_DANGER: Final[int] = 10

DIAL_MOD: Final[int] = (
    max(COST_ROAD, COST_EMPTY, COST_UNSEEN, COST_DANGER + COST_EMPTY) + 2
)


# -- Symmetry --
class Symmetry(IntEnum):
    ROT = 1
    HOR = 2
    VER = 3


# -- Roles --
class Role(IntEnum):
    ECON = 0
    RUSH = 1
    HOME = 2
    FLEX = 3


# -- Directions --
DIR4: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
DIR4_DELTA: tuple[tuple[int, int], ...] = tuple(d.delta() for d in DIR4)

DIR8: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
)
DIR8_DELTA: tuple[tuple[int, int], ...] = tuple(d.delta() for d in DIR8)
DIR8_IDX: dict[Direction, int] = {d: i for i, d in enumerate(DIR8)}

DELTA_TO_DIR: dict[tuple[int, int], Direction] = {d.delta(): d for d in DIR8}

BRIDGE_DELTAS: tuple[tuple[int, int], ...] = tuple(
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 0 < dx * dx + dy * dy <= 9 and abs(dx) + abs(dy) != 1
)

# -- Role schedule for core spawning --
ROLE_SCHEDULE: tuple[Role, ...] = (
    Role.ECON,  # spawn 0
    Role.ECON,  # spawn 1
    Role.RUSH,  # spawn 2
    Role.RUSH,  # spawn 3
    Role.HOME,  # spawn 4
    Role.FLEX,  # spawn 5
)

BUILDER_CAP: Final[int] = 6

# -- Gunner constants --
GUNNER_RANGE_SQ: Final[int] = 13
MIN_GUNNER_FLOW: Final[float] = 0.05
