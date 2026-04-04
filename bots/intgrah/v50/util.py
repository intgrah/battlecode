from enum import StrEnum
from typing import Final

from cambc import Direction, Position

INF: Final[int] = 1_000_000

COST_ROAD: Final[int] = 1
COST_EMPTY: Final[int] = 3
COST_UNSEEN: Final[int] = 3
COST_IMPASSABLE: Final[int] = INF

# The number of buckets used in Dial's algorithm must exceed the maximum possible increase in f-value in A*.
# f(n) = g(n) + h(n)
# We take the maximum edge cost, plus one, because the Chebyshev heuristic can change by at most one, and then plus one again, so that it is greater than this number.
DIAL_MOD: Final[int] = max(COST_ROAD, COST_EMPTY, COST_UNSEEN) + 1 + 1


class Symmetry(StrEnum):
    ROT = "rot"
    HOR = "hor"
    VER = "ver"


DIR4 = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
DIR4_DELTA = [c.delta() for c in DIR4]
DIR8 = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
DIR8_DELTA = [c.delta() for c in DIR8]
DIR8_IDX = {d: i for i, d in enumerate(DIR8)}

BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 0 < dx * dx + dy * dy <= 9 and abs(dx) + abs(dy) != 1
]

DELTA_TO_DIR = {
    (0, -1): Direction.NORTH,
    (1, -1): Direction.NORTHEAST,
    (1, 0): Direction.EAST,
    (1, 1): Direction.SOUTHEAST,
    (0, 1): Direction.SOUTH,
    (-1, 1): Direction.SOUTHWEST,
    (-1, 0): Direction.WEST,
    (-1, -1): Direction.NORTHWEST,
}


def rotate_cw(d: Direction, steps: int) -> Direction:
    return DIR8[(DIR8_IDX[d] + steps) % 8]


def tiles_3x3(core: Position) -> set[Position]:
    return {core} | {core.add(d) for d in DIR8}
