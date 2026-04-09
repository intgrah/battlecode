from __future__ import annotations

from typing import override

from cambc import Controller, EntityType, GameConstants, Position
from unit import StationaryUnit

__all__ = ["Sentinel"]

PRIORITY: dict[EntityType, int] = {
    EntityType.BUILDER_BOT: 12,
    EntityType.SPLITTER: 11,
    EntityType.BRIDGE: 10,
    EntityType.BREACH: 9,
    EntityType.SENTINEL: 8,
    EntityType.GUNNER: 7,
    EntityType.LAUNCHER: 6,
    EntityType.CONVEYOR: 5,
    EntityType.ARMOURED_CONVEYOR: 4,
    EntityType.CORE: 3,
    EntityType.FOUNDRY: 2,
    EntityType.BARRIER: 1,
    EntityType.ROAD: 0,
}


class Sentinel(StationaryUnit):
    @override
    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return

        best_score = -1
        best_target: Position | None = None
        for entity in ct.get_nearby_entities():
            result = self._score_entity(ct, entity)
            if result is not None:
                score, target = result
                if score > best_score:
                    best_score = score
                    best_target = target

        if best_target is not None:
            ct.fire(best_target)

    def _score_entity(
        self,
        ct: Controller,
        eid: int,
    ) -> tuple[int, Position] | None:
        if ct.get_team(eid) == self.my_team:
            return None
        etype = ct.get_entity_type(eid)
        if etype == EntityType.MARKER:
            return None

        fire_pos = ct.get_position(eid)

        if etype == EntityType.CORE:
            closer = fire_pos.add(fire_pos.direction_to(self.my_pos))
            if ct.can_fire(closer):
                fire_pos = closer

        if not ct.can_fire(fire_pos):
            return None

        uid = ct.get_tile_builder_bot_id(fire_pos)
        if uid is not None and ct.get_team(uid) == self.my_team:
            return None

        score = PRIORITY.get(etype, 0)
        if ct.get_hp(eid) <= GameConstants.SENTINEL_DAMAGE:
            score += 1

        return score, fire_pos
