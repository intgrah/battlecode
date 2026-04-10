"""Launcher turret logic — launch enemy builders away or onto the enemy core."""

from __future__ import annotations

from cambc import Controller, EntityType, Position
from unit import Unit
from utils import _ALL_DIRS


class Launcher(Unit):
    def __init__(self, ct: Controller) -> None:
        self._enemy_core: Position | None = None

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return

        # Scan for enemy core if not yet found.
        if self._enemy_core is None:
            my_team = ct.get_team()
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) == EntityType.CORE
                    and ct.get_team(bid) != my_team
                ):
                    self._enemy_core = ct.get_position(bid)
                    break

        pos = ct.get_position()
        my_team = ct.get_team()

        w = ct.get_map_width()
        h = ct.get_map_height()

        # Find adjacent enemy builder bots.
        for uid in ct.get_nearby_units(2):
            if ct.get_team(uid) == my_team:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            bot_pos = ct.get_position(uid)

            # If enemy core is known, try to throw onto or adjacent to it.
            if self._enemy_core is not None:
                if ct.can_launch(bot_pos, self._enemy_core):
                    ct.launch(bot_pos, self._enemy_core)
                    return
                for d in _ALL_DIRS:
                    adj = self._enemy_core.add(d)
                    if 0 <= adj.x < w and 0 <= adj.y < h and ct.can_launch(bot_pos, adj):
                        ct.launch(bot_pos, adj)
                        return

            # Otherwise, throw as far away as possible.
            best: Position | None = None
            best_dist = -1
            for tile in ct.get_attackable_tiles():
                if not ct.can_launch(bot_pos, tile):
                    continue
                dist = pos.distance_squared(tile)
                if dist > best_dist:
                    best = tile
                    best_dist = dist

            if best is not None:
                ct.launch(bot_pos, best)
                return
