from enum import Enum, auto
from typing import Final

from cambc import Direction, Position

INF: Final[int] = 1_000_000

COST_ROAD: Final[int] = 1
COST_EMPTY: Final[int] = 3
COST_UNSEEN: Final[int] = 3
COST_IMPASSABLE: Final[int] = INF


class Symmetry(Enum):
    ROT = auto()
    HOR = auto()
    VER = auto()


DIR4 = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
DIR4_DELTA: tuple[tuple[int, int], ...] = tuple(d.delta() for d in DIR4)

DIR8 = (
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

BRIDGE_DELTAS: tuple[tuple[int, int], ...] = tuple(
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 0 < dx * dx + dy * dy <= 9 and abs(dx) + abs(dy) != 1
)

DELTA_TO_DIR: dict[tuple[int, int], Direction] = {
    (0, -1): Direction.NORTH,
    (1, -1): Direction.NORTHEAST,
    (1, 0): Direction.EAST,
    (1, 1): Direction.SOUTHEAST,
    (0, 1): Direction.SOUTH,
    (-1, 1): Direction.SOUTHWEST,
    (-1, 0): Direction.WEST,
    (-1, -1): Direction.NORTHWEST,
}


def chebyshev(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def tiles_3x3(core: Position) -> set[Position]:
    return {core} | {core.add(d) for d in DIR8}
