from __future__ import annotations

from enum import StrEnum

from cambc import Direction, Position

INF: int = 1_000_000


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
DIR8_IDX: dict[Direction, int] = {d: i for i, d in enumerate(DIR8)}

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

BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 0 < dx * dx + dy * dy <= 9 and abs(dx) + abs(dy) != 1
]


def rotate_cw(d: Direction, steps: int) -> Direction:
    return DIR8[(DIR8_IDX[d] + steps) % 8]


def tiles_3x3(core: Position) -> set[Position]:
    return {core} | {core.add(d) for d in DIR8}
