from __future__ import annotations

from typing import override

from cambc import Controller, EntityType, GameConstants, Position
from unit import Unit

__all__ = ["Sentinel"]

_PRIORITY: dict[EntityType, int] = {
    EntityType.BUILDER_BOT: 10,
    EntityType.SPLITTER: 9,
    EntityType.BRIDGE: 8,
    EntityType.BREACH: 7,
    EntityType.SENTINEL: 6,
    EntityType.GUNNER: 5,
    EntityType.LAUNCHER: 4,
    EntityType.CONVEYOR: 3,
    EntityType.ARMOURED_CONVEYOR: 3,
    EntityType.CORE: 2,
    EntityType.FOUNDRY: 2,
    EntityType.BARRIER: 1,
    EntityType.ROAD: 1,
}


class Sentinel(Unit):
    @override
    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return

        my_pos = ct.get_position()

        best_score = -1
        best_target: Position | None = None
        for entity in ct.get_nearby_entities():
            if ct.get_team(entity) == self.my_team:
                continue
            result = self._score_entity(ct, my_pos, entity)
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
        my_pos: Position,
        entity: int,
    ) -> tuple[int, Position] | None:
        etype = ct.get_entity_type(entity)
        if etype == EntityType.MARKER:
            return None

        entity_pos = ct.get_position(entity)
        fire_pos = entity_pos

        if etype == EntityType.CORE:
            closer = entity_pos.add(entity_pos.direction_to(my_pos))
            if ct.can_fire(closer):
                fire_pos = closer

        # Don't hit friendly builders
        if not ct.can_fire(fire_pos):
            return None

        uid = ct.get_tile_builder_bot_id(fire_pos)
        if uid is not None and ct.get_team(uid) == self.my_team:
            return None

        score = _PRIORITY.get(etype, 0)
        if ct.get_hp(entity) <= GameConstants.SENTINEL_DAMAGE:
            score += 1

        return score, fire_pos
