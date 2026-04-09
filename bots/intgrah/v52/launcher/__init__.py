from __future__ import annotations

from typing import override

from cambc import Controller, EntityType, Environment, Position
from unit import StationaryUnit
from util import DIR4, DIR8

__all__ = ["Launcher"]

_PASSABLE_BUILDINGS = frozenset(
    {
        EntityType.ARMOURED_CONVEYOR,
        EntityType.BRIDGE,
        EntityType.CONVEYOR,
        EntityType.ROAD,
        EntityType.SPLITTER,
    },
)


class Launcher(StationaryUnit):
    @override
    def run(self, ct: Controller) -> None:

        enemy_throw_tile, enemy_throw_dist = self.find_enemy_throw_tile(ct, self.my_pos)
        harvester_targets = self.find_harvester_attack_tiles(ct)
        harvest_dest = harvester_targets[0] if harvester_targets else None

        best_bot: Position | None = None
        best_dest: Position | None = None
        best_score = 0

        for uid in ct.get_nearby_units(2):
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

    def is_walkable(self, ct: Controller, pos: Position) -> bool:
        if (
            not self.in_bounds(pos)
            or not ct.is_in_vision(pos)
            or ct.get_tile_env(pos) == Environment.WALL
        ):
            return False
        bid = ct.get_tile_building_id(pos)
        return bid is not None and ct.get_entity_type(bid) in _PASSABLE_BUILDINGS

    def is_empty_walkable(self, ct: Controller, pos: Position) -> bool:
        return self.is_walkable(ct, pos) and ct.get_tile_builder_bot_id(pos) is None

    def find_enemy_throw_tile(
        self, ct: Controller, my_pos: Position
    ) -> tuple[Position | None, int]:
        best: Position | None = None
        best_dist = 0
        for pos in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(pos)
            if not self.is_empty_walkable(ct, pos):
                continue
            if bid is not None and ct.get_team(bid) == self.my_team:
                continue
            dist = my_pos.distance_squared(pos)
            if dist > best_dist:
                best_dist = dist
                best = pos
        return best, best_dist

    def find_harvester_attack_tiles(self, ct: Controller) -> list[Position]:
        targets: list[Position] = []
        for pos in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(pos)
            if (
                bid is None
                or ct.get_entity_type(bid) != EntityType.HARVESTER
                or ct.get_team(bid) == self.my_team
            ):
                continue
            for d in DIR4:
                adj = pos.add(d)
                adj_bid = ct.get_tile_building_id(pos)
                if (
                    self.is_empty_walkable(ct, adj)
                    and adj_bid is not None
                    and ct.get_team(adj_bid) != self.my_team
                ):
                    targets.append(adj)
                elif (
                    adj.x < 0
                    or adj.x >= ct.get_map_width()
                    or adj.y < 0
                    or adj.y >= ct.get_map_height()
                    or not ct.is_in_vision(adj)
                    or ct.get_tile_building_id(adj) is None
                ):
                    for d2 in DIR8:
                        adj2 = pos.add(d2)
                        if self.is_empty_walkable(ct, adj2):
                            targets.append(adj2)
                    break
        return targets
