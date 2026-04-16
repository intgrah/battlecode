from collections.abc import Iterable
from enum import StrEnum
from typing import Final

from cambc import Direction, EntityType, GameConstants, Position


class Symmetry(StrEnum):
    ROT = "rot"
    HOR = "hor"
    VER = "ver"


INF: Final = 1_000_000
ROAD_COST: Final = 3

DIR8: Final = [d for d in Direction if d != Direction.CENTRE]
DIR4: Final = [
    Direction.NORTH,
    Direction.SOUTH,
    Direction.EAST,
    Direction.WEST,
]
DIR8_DELTA: Final = [c.delta() for c in DIR8]

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


def get_direction_object(from_pos: Position, to_pos: Position) -> Direction | None:
    return DELTA_TO_DIR.get((to_pos.x - from_pos.x, to_pos.y - from_pos.y))


def chebyshev(pos1: Position, pos2: Position) -> int:
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


BASE_COST: Final = {
    EntityType.BUILDER_BOT: GameConstants.BUILDER_BOT_BASE_COST,
    EntityType.HARVESTER: GameConstants.HARVESTER_BASE_COST,
    EntityType.SENTINEL: GameConstants.SENTINEL_BASE_COST,
    EntityType.GUNNER: GameConstants.GUNNER_BASE_COST,
    EntityType.LAUNCHER: GameConstants.LAUNCHER_BASE_COST,
    EntityType.CONVEYOR: GameConstants.CONVEYOR_BASE_COST,
    EntityType.BRIDGE: GameConstants.BRIDGE_BASE_COST,
    EntityType.SPLITTER: GameConstants.SPLITTER_BASE_COST,
    EntityType.BARRIER: GameConstants.BARRIER_BASE_COST,
}


def closest(target: Position, positions: Iterable[Position]) -> Position | None:
    return min(positions, key=target.distance_squared, default=None)
