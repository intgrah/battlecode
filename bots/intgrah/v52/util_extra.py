from cambc import Controller, Direction, EntityType, GameConstants, Position
from util import DELTA_TO_DIR


def get_direction_object(from_pos: Position, to_pos: Position) -> Direction | None:
    return DELTA_TO_DIR.get((to_pos.x - from_pos.x, to_pos.y - from_pos.y))


def try_move(ct: Controller, target_pos: Position) -> bool:
    d = get_direction_object(ct.get_position(), target_pos)
    if d is not None and ct.can_move(d):
        ct.move(d)
        return True
    return False


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
    },
)
_EARLY_GAME_ROUND = 35
_HARVESTER_RESERVE_EARLY = 10
_HARVESTER_RESERVE_LATE = 20
_LAUNCHER_RESERVE = 15


def can_afford(ct: Controller, etype: EntityType) -> bool:
    ti, _ = ct.get_global_resources()
    ti_cost, _ax_cost = BASE_COST[etype]
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
        return ti >= (ti_cost + reserve) * (1 + scale)
    return ti >= ti_cost * scale


def closest(target: Position, positions: list[Position]) -> Position | None:
    if len(positions) == 0:
        return None
    return min(positions, key=target.distance_squared)
