from __future__ import annotations

from typing import override

from cambc import Controller, Direction, EntityType, Environment, Position, Team
from unit import Unit

__all__ = ["Launcher"]

_DIR8: list[Direction] = [d for d in Direction if d != Direction.CENTRE]
_DIR4: list[Direction] = [
    Direction.NORTH,
    Direction.SOUTH,
    Direction.EAST,
    Direction.WEST,
]
_PASSABLE_BUILDINGS = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ROAD,
        EntityType.SPLITTER,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.BRIDGE,
    }
)


def _is_walkable(ct: Controller, pos: Position) -> bool:
    if (
        pos.x < 0
        or pos.x >= ct.get_map_width()
        or pos.y < 0
        or pos.y >= ct.get_map_height()
        or not ct.is_in_vision(pos)
    ):
        return False
    if ct.get_tile_env(pos) == Environment.WALL:
        return False
    bid = ct.get_tile_building_id(pos)
    return bid is not None and ct.get_entity_type(bid) in _PASSABLE_BUILDINGS


def _is_empty_walkable(ct: Controller, pos: Position) -> bool:
    return _is_walkable(ct, pos) and ct.get_tile_builder_bot_id(pos) is None


def _find_enemy_throw_tile(
    ct: Controller, my_pos: Position, my_team: Team
) -> tuple[Position | None, int]:
    best: Position | None = None
    best_dist = 0
    for pos in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(pos)
        if not _is_empty_walkable(ct, pos):
            continue
        if bid is not None and ct.get_team(bid) == my_team:
            continue
        dist = my_pos.distance_squared(pos)
        if dist > best_dist:
            best_dist = dist
            best = pos
    return best, best_dist


def _find_harvester_attack_tiles(ct: Controller, my_team: Team) -> list[Position]:
    """Tiles adjacent to enemy harvesters that a launcher can drop a
    friendly builder onto — must be a walkable tile owned by the
    enemy (so our bot can land and destroy it by firing). If the
    only neighbours are friendly or empty, no target here.
    """
    targets: list[Position] = []
    for pos in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(pos)
        if bid is None or ct.get_entity_type(bid) != EntityType.HARVESTER:
            continue
        if ct.get_team(bid) == my_team:
            continue
        for d in _DIR4:
            adj = pos.add(d)
            if not _is_empty_walkable(ct, adj):
                continue
            adj_bid = ct.get_tile_building_id(adj)
            if adj_bid is None or ct.get_team(adj_bid) == my_team:
                continue
            targets.append(adj)
    return targets


class Launcher(Unit):
    @override
    def __init__(self, _ct: Controller) -> None:
        pass

    @override
    def run(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        my_team = ct.get_team()

        enemy_throw_tile, enemy_throw_dist = _find_enemy_throw_tile(ct, my_pos, my_team)
        harvester_targets = _find_harvester_attack_tiles(ct, my_team)
        harvest_dest = harvester_targets[0] if harvester_targets else None

        best_bot: Position | None = None
        best_dest: Position | None = None
        best_score = 0

        for uid in ct.get_nearby_units(2):
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue

            score = 0
            dest: Position | None = None

            if ct.get_team(uid) == my_team and harvest_dest is not None:
                score = 8
                dest = harvest_dest
            elif ct.get_team(uid) != my_team and enemy_throw_tile is not None:
                score = enemy_throw_dist
                dest = enemy_throw_tile

            if score > best_score:
                best_bot = ct.get_position(uid)
                best_dest = dest
                best_score = score

        if (
            best_bot is not None
            and best_dest is not None
            and ct.can_launch(best_bot, best_dest)
        ):
            ct.launch(best_bot, best_dest)
