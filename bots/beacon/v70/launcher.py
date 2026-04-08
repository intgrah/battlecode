"""Launcher AI: throw enemy builder bots away from our attack zone.

Scans adjacent tiles for enemy bots and launches them to the tile
that maximizes distance from this launcher (disrupts enemy healing/defense).
"""

from __future__ import annotations

from cambc import Controller, EntityType, Position
from unit import Unit

_IDLE_LIMIT = 30


class Launcher(Unit):
    def __init__(self, ct: Controller) -> None:
        self._idle_rounds = 0

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        my_team = ct.get_team()
        pos = ct.get_position()
        w = ct.get_map_width()
        h = ct.get_map_height()

        # Find adjacent enemy builder bots (pickup r²=2)
        enemy_bots: list[Position] = []
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            upos = ct.get_position(uid)
            if pos.distance_squared(upos) <= 2:
                enemy_bots.append(upos)

        if not enemy_bots:
            self._idle_rounds += 1
            if self._idle_rounds >= _IDLE_LIMIT:
                # No enemies around for a long time -- self-destruct to free scale
                ct.self_destruct()
            return

        # For each enemy bot, find the best throw target (farthest from launcher)
        for bot_pos in enemy_bots:
            best_target: Position | None = None
            best_dist = -1
            # Scan all tiles within throw range (r²≤26)
            for dx in range(-5, 6):
                for dy in range(-5, 6):
                    d2 = dx * dx + dy * dy
                    if d2 == 0 or d2 > 26:
                        continue
                    tx, ty = pos.x + dx, pos.y + dy
                    if not (0 <= tx < w and 0 <= ty < h):
                        continue
                    tpos = Position(tx, ty)
                    if not ct.is_tile_passable(tpos):
                        continue
                    if not ct.can_launch(bot_pos, tpos):
                        continue
                    # Maximize distance from launcher (send them far away)
                    if d2 > best_dist:
                        best_dist = d2
                        best_target = tpos

            if best_target is not None:
                ct.launch(bot_pos, best_target)
                self._idle_rounds = 0
                return

        self._idle_rounds += 1
