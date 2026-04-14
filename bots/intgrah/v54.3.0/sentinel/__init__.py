from __future__ import annotations

from typing import Final, override

from cambc import Controller, EntityType, GameConstants, Position
from unit import StationaryUnit

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


class Sentinel(StationaryUnit):
    SELF_DESTRUCT_THRESHOLD: Final[int] = 16

    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.idle_turns: int = 0

    @override
    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return

        best_score = -1
        best_target: Position | None = None

        for tile in ct.get_attackable_tiles():
            bid = ct.get_tile_building_id(tile)
            uid = ct.get_tile_builder_bot_id(tile)

            if uid is not None and ct.get_team(uid) != self.my_team:
                score = _PRIORITY[EntityType.BUILDER_BOT]
                if ct.get_hp(uid) <= GameConstants.SENTINEL_DAMAGE:
                    score += 1
                if score > best_score:
                    best_score = score
                    best_target = tile
                continue

            if uid is not None and ct.get_team(uid) == self.my_team:
                continue

            if bid is None:
                continue
            if ct.get_team(bid) == self.my_team:
                continue
            etype = ct.get_entity_type(bid)
            if etype in (EntityType.MARKER, EntityType.HARVESTER):
                continue
            score = _PRIORITY.get(etype, 0)
            if ct.get_hp(bid) <= GameConstants.SENTINEL_DAMAGE:
                score += 1
            if score > best_score:
                best_score = score
                best_target = tile

        if best_target is not None and ct.can_fire(best_target):
            ct.fire(best_target)
            self.idle_turns = 0
        else:
            self.idle_turns += 1
            if self.idle_turns > Sentinel.SELF_DESTRUCT_THRESHOLD:
                self.try_self_destruct(ct)

    def try_self_destruct(self, ct: Controller) -> None:
        has_ally = False
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == self.my_team:
                has_ally = True
            else:
                return
        if has_ally:
            ct.self_destruct()
