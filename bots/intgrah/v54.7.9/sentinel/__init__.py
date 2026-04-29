from __future__ import annotations

from typing import Final, override

from cambc import Controller, EntityType, GameConstants, Position, Team
from unit import Unit

__all__ = ["Sentinel"]


_ENEMY_COMBAT: frozenset[EntityType] = frozenset(
    {
        EntityType.CORE,
        EntityType.BREACH,
        EntityType.SENTINEL,
        EntityType.GUNNER,
        EntityType.LAUNCHER,
    },
)


def _feeds_enemy_combat(ct: Controller, my_team: Team, outputs: list[Position]) -> bool:
    for out in outputs:
        out_bid = ct.get_tile_building_id(out)
        if out_bid is None:
            continue
        if ct.get_team(out_bid) == my_team:
            continue
        if ct.get_entity_type(out_bid) in _ENEMY_COMBAT:
            return True
    return False


def _transport_outputs(ct: Controller, bid: int, pos: Position, etype: EntityType) -> list[Position]:
    if etype == EntityType.BRIDGE:
        return [ct.get_bridge_target(bid)]
    d = ct.get_direction(bid)
    if etype == EntityType.SPLITTER:
        return [
            pos.add(d),
            pos.add(d.rotate_right().rotate_right()),
            pos.add(d.rotate_left().rotate_left()),
        ]
    return [pos.add(d)]


_TRANSPORT: frozenset[EntityType] = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)


_PRIORITY: dict[EntityType, int] = {
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


def _builder_score(hp: int) -> int:
    if hp <= GameConstants.SENTINEL_DAMAGE:
        return 15
    if hp < GameConstants.BUILDER_BOT_MAX_HP:
        return 7
    return 5


class Sentinel(Unit):
    SELF_DESTRUCT_THRESHOLD: Final[int] = 16

    @override
    def __init__(self) -> None:
        super().__init__()
        self.idle_turns: int = 0

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        if ct.get_action_cooldown() > 0:
            return

        best_score = -1
        best_target: Position | None = None

        for tile in ct.get_attackable_tiles():
            bid = ct.get_tile_building_id(tile)
            uid = self.all_bots.get(tile)

            if tile in self.enemy_bots:
                score = _builder_score(ct.get_hp(uid))
                if score > best_score:
                    best_score = score
                    best_target = tile
                continue

            if tile in self.friendly_bots:
                continue

            if bid is None:
                continue
            if ct.get_team(bid) == self.my_team:
                continue
            etype = ct.get_entity_type(bid)
            if etype in (EntityType.MARKER, EntityType.HARVESTER):
                continue
            score = _PRIORITY.get(etype, 0)
            if etype in _TRANSPORT and _feeds_enemy_combat(
                ct,
                self.my_team,
                _transport_outputs(ct, bid, tile, etype),
            ):
                score = 12
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
