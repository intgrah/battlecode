from __future__ import annotations

from typing import override

from cambc import Controller, EntityType, Environment, Position
from unit import Unit

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

        farthest_dest = self._farthest_throw_dest(ct)
        if farthest_dest is None:
            return

        best_bot: Position | None = None
        best_dist = -1

        for uid in ct.get_nearby_units():
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(uid) == self.my_team:
                continue
            bot_pos = ct.get_position(uid)
            if not ct.can_launch(bot_pos, farthest_dest):
                continue
            d = self.my_pos.distance_squared(bot_pos)
            if d > best_dist:
                best_dist = d
                best_bot = bot_pos

        if best_bot is not None:
            ct.launch(best_bot, farthest_dest)

    def _is_empty_walkable(self, ct: Controller, pos: Position) -> bool:
        if not self.in_bounds(pos) or not ct.is_in_vision(pos):
            return False
        if ct.get_tile_env(pos) == Environment.WALL:
            return False
        bid = ct.get_tile_building_id(pos)
        if bid is None or ct.get_entity_type(bid) not in _PASSABLE_BUILDINGS:
            return False
        return pos not in self.all_bots

    def _farthest_throw_dest(self, ct: Controller) -> Position | None:
        best: Position | None = None
        best_dist = -1
        for pos in self.nearby_tiles:
            if not self._is_empty_walkable(ct, pos):
                continue
            dist = self.my_pos.distance_squared(pos)
            if dist > best_dist:
                best_dist = dist
                best = pos
        return best
