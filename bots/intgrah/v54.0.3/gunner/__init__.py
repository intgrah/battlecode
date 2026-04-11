from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Controller, EntityType
from unit import Unit

if TYPE_CHECKING:
    from cambc import Direction

__all__ = ["Gunner"]

_SELF_DESTRUCT_THRESHOLD: int = 10
# Gunner attack r²=13 → cardinal range 3 tiles, diagonal range 2 tiles.
_GUNNER_R2: int = 13


def _firing_path_clear(ct: Controller) -> bool:
    """Trace along our facing ray. Return False if any friendly bot or
    non-marker friendly building would absorb our shot first. The
    engine fires at the FIRST blocker in the ray, friend or foe, so a
    friendly sentinel sitting in the line of fire eats the projectile
    before it reaches the enemy we were aiming at.
    """
    my_team = ct.get_team()
    my_id = ct.get_id()
    my_pos = ct.get_position(my_id)
    facing = ct.get_direction(my_id)
    cur = my_pos
    for _ in range(3):
        cur = cur.add(facing)
        if cur.distance_squared(my_pos) > _GUNNER_R2:
            return True
        bid = ct.get_tile_building_id(cur)
        if bid is not None:
            if ct.get_team(bid) == my_team:
                if ct.get_entity_type(bid) != EntityType.MARKER:
                    return False
            else:
                return True
        uid = ct.get_tile_builder_bot_id(cur)
        if uid is not None:
            return ct.get_team(uid) != my_team
    return True


class Gunner(Unit):
    @override
    def __init__(self, ct: Controller) -> None:
        self.idle_turns: int = 0

    @override
    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()

        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            bid = ct.get_tile_building_id(target)
            uid = ct.get_tile_builder_bot_id(target)
            is_enemy_building = bid is not None and ct.get_team(bid) != my_team
            is_enemy_bot = uid is not None and ct.get_team(uid) != my_team
            is_friendly = (bid is not None and ct.get_team(bid) == my_team) or (
                uid is not None and ct.get_team(uid) == my_team
            )
            if (
                not is_friendly
                and (is_enemy_building or is_enemy_bot)
                and _firing_path_clear(ct)
            ):
                ct.fire(target)
                self.idle_turns = 0
                return

        if self._try_rotate_to_enemy(ct):
            self.idle_turns = 0
        else:
            self.idle_turns += 1

        if self.idle_turns > _SELF_DESTRUCT_THRESHOLD:
            self._try_self_destruct(ct)

    def _try_rotate_to_enemy(self, ct: Controller) -> bool:
        my_team = ct.get_team()
        my_pos = ct.get_position()
        best_dist = float("inf")
        best_dir: Direction | None = None
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            match ct.get_entity_type(bid):
                case EntityType.SENTINEL | EntityType.GUNNER | EntityType.LAUNCHER:
                    bp = ct.get_position(bid)
                    dist = my_pos.distance_squared(bp)
                    if dist < best_dist:
                        best_dist = dist
                        best_dir = my_pos.direction_to(bp)
        if best_dir is not None and ct.can_rotate(best_dir):
            ct.rotate(best_dir)
            return True
        return False

    def _try_self_destruct(self, ct: Controller) -> None:
        if ct.get_unit_count() < 35:
            return
        my_team = ct.get_team()
        has_ally = False
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                has_ally = True
            else:
                return
        if has_ally:
            ct.self_destruct()
