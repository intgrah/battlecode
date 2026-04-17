from __future__ import annotations

from typing import override

from cambc import Controller, EntityType, Environment, Position
from unit import Unit
from util import DIR4

__all__ = ["Launcher"]


_PASSABLE_BUILDINGS = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ROAD,
        EntityType.SPLITTER,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.BRIDGE,
    },
)


class Launcher(Unit):
    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        enemy_throw_tile, enemy_throw_dist = self.find_enemy_throw_tile(ct)
        harvester_targets = self.find_harvester_attack_tiles(ct)
        harvest_dest = harvester_targets[0] if harvester_targets else None

        best_bot: Position | None = None
        best_dest: Position | None = None
        best_score = 0

        for uid in ct.get_nearby_units():
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue

            score = 0
            dest: Position | None = None

            if ct.get_team(uid) == self.my_team and harvest_dest is not None:
                score = 8
                dest = harvest_dest
            elif ct.get_team(uid) != self.my_team and enemy_throw_tile is not None:
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

    def is_empty_walkable(self, ct: Controller, pos: Position) -> bool:
        return self.is_walkable(ct, pos) and pos not in self.all_bots

    def is_walkable(self, ct: Controller, pos: Position) -> bool:
        if not self.in_bounds(pos) or not ct.is_in_vision(pos):
            return False
        if ct.get_tile_env(pos) == Environment.WALL:
            return False
        bid = ct.get_tile_building_id(pos)
        return bid is not None and ct.get_entity_type(bid) in _PASSABLE_BUILDINGS

    def find_harvester_attack_tiles(self, ct: Controller) -> list[Position]:
        """Tiles adjacent to enemy harvesters that a launcher can drop a
        friendly builder onto — must be a walkable tile owned by the
        enemy (so our bot can land and destroy it by firing). If the
        only neighbours are friendly or empty, no target here.
        """
        targets: list[Position] = []
        for pos in self.nearby_tiles:
            bid = ct.get_tile_building_id(pos)
            if bid is None or ct.get_entity_type(bid) != EntityType.HARVESTER:
                continue
            if ct.get_team(bid) == self.my_team:
                continue
            for d in DIR4:
                adj = pos.add(d)
                if not self.is_empty_walkable(ct, adj):
                    continue
                adj_bid = ct.get_tile_building_id(adj)
                if adj_bid is None or ct.get_team(adj_bid) == self.my_team:
                    continue
                targets.append(adj)
        return targets

    def find_enemy_throw_tile(self, ct: Controller) -> tuple[Position | None, int]:
        best: Position | None = None
        best_dist = 0
        for pos in self.nearby_tiles:
            bid = ct.get_tile_building_id(pos)
            if not self.is_empty_walkable(ct, pos):
                continue
            if bid is not None and ct.get_team(bid) == self.my_team:
                continue
            dist = self.my_pos.distance_squared(pos)
            if dist > best_dist:
                best_dist = dist
                best = pos
        return best, best_dist
