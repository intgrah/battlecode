from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Final

from cambc import Controller, Direction, EntityType, GameConstants

if TYPE_CHECKING:
    from builder import Builder, PosInt


class Symmetry(StrEnum):
    ROT = "rot"
    HOR = "hor"
    VER = "ver"


INF: Final[int] = 1_000_000

# Assuming dist_stride = 100
DIR4 = (
    -100,  # North
    100,  # South
    1,  # East
    -1,  # West
)

DIR8 = (
    -100,  # North
    -100 + 1,  # Northeast
    1,  # East
    100 + 1,  # Southeast
    100,  # South
    100 - 1,  # Southwest
    -1,  # West
    -100 - 1,  # Northwest
)
DIR8_DELTA = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))

DELTA_TO_DIR: dict[int, Direction] = {
    0: Direction.CENTRE,
    -100: Direction.NORTH,
    -99: Direction.NORTHEAST,
    1: Direction.EAST,
    101: Direction.SOUTHEAST,
    100: Direction.SOUTH,
    99: Direction.SOUTHWEST,
    -1: Direction.WEST,
    -101: Direction.NORTHWEST,
}

DIR_TO_DELTA: dict[Direction, int] = {v: k for k, v in DELTA_TO_DIR.items()}


def get_direction_object(from_pos: int, to_pos: int) -> Direction:
    # 1. Decode the positions using the stride
    y1, x1 = divmod(from_pos, 100)
    y2, x2 = divmod(to_pos, 100)

    # 2. Find the raw difference
    dx = x2 - x1
    dy = y2 - y1

    # 3. Normalize dx and dy to [-1, 0, 1]
    # This turns any distance into a single-step "unit delta"
    norm_dx = (dx > 0) - (dx < 0)
    norm_dy = (dy > 0) - (dy < 0)

    # 4. If there's no movement at all, return None
    if norm_dx == 0 and norm_dy == 0:
        return Direction.CENTRE

    # 5. Re-encode the normalized delta to match your dictionary keys
    # (y * stride + x)
    unit_delta = (norm_dy * 100) + norm_dx

    return DELTA_TO_DIR[unit_delta]


def try_move(self: Builder, ct: Controller, target_pos: PosInt) -> bool:
    delta = target_pos - self.my_pos
    d = DELTA_TO_DIR.get(delta)
    if d is not None and ct.can_move(d):
        ct.move(d)
        self.my_pos = target_pos
        return True
    return False


def reachable_path_end(
    self: Builder, path: list[PosInt], current_pos: PosInt, max_range: int
) -> PosInt:
    for pos in reversed(path):
        if self.sq_dist(current_pos, pos) <= max_range**2 and self.is_passable(
            pos
        ):  # TODO: is_reachable
            return pos
    return current_pos


BASE_COST: dict[EntityType, tuple[int, int]] = {
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
_IS_UNIT = frozenset(
    {
        EntityType.BUILDER_BOT,
        EntityType.HARVESTER,
        EntityType.SENTINEL,
        EntityType.GUNNER,
        EntityType.LAUNCHER,
    }
)
_EARLY_GAME_ROUND = 35
_HARVESTER_RESERVE_EARLY = 10
_HARVESTER_RESERVE_LATE = 20
_LAUNCHER_RESERVE = 15


def can_afford(ct: Controller, etype: EntityType) -> bool:
    ti, ax = ct.get_global_resources()
    ti_cost, ax_cost = BASE_COST[etype]
    scale = ct.get_scale_percent() / 100
    if etype in _IS_UNIT:
        reserve = 0
        if etype == EntityType.HARVESTER:
            reserve = (
                _HARVESTER_RESERVE_EARLY
                if ct.get_current_round() < _EARLY_GAME_ROUND
                else _HARVESTER_RESERVE_LATE
            )
        elif etype == EntityType.LAUNCHER:
            reserve = _LAUNCHER_RESERVE
        return ti >= (ti_cost + reserve) * (1 + scale) and ax >= ax_cost * scale
    return ti >= ti_cost * scale and ax >= ax_cost * scale


def closest(self: Builder, target: PosInt, positions: list[PosInt]) -> PosInt:
    if not positions:
        return -1
    return min(positions, key=lambda x: self.sq_dist(target, x))
