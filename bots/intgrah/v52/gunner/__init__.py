from __future__ import annotations

from typing import TYPE_CHECKING, Final, override

from cambc import Controller, EntityType
from unit import StationaryUnit

if TYPE_CHECKING:
    from cambc import Direction

__all__ = ["Gunner"]


class Gunner(StationaryUnit):
    SELF_DESTRUCT_THRESHOLD: Final[int] = 10

    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.idle_turns: int = 0

    @override
    def run(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            bid = ct.get_tile_building_id(target)
            uid = ct.get_tile_builder_bot_id(target)
            is_enemy_building = bid is not None and ct.get_team(bid) != self.my_team
            is_enemy_bot = uid is not None and ct.get_team(uid) != self.my_team
            is_friendly = (bid is not None and ct.get_team(bid) == self.my_team) or (
                uid is not None and ct.get_team(uid) == self.my_team
            )
            if not is_friendly and (is_enemy_building or is_enemy_bot):
                ct.fire(target)
                self.idle_turns = 0
                return

        if self.try_rotate_to_enemy(ct):
            self.idle_turns = 0
        else:
            self.idle_turns += 1

        if not self.is_fed(ct):
            self.idle_turns = 0

        if self.idle_turns > Gunner.SELF_DESTRUCT_THRESHOLD:
            self.try_self_destruct(ct)

    def try_rotate_to_enemy(self, ct: Controller) -> bool:
        best_dist = float("inf")
        best_dir: Direction | None = None
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == self.my_team:
                continue
            match ct.get_entity_type(bid):
                case EntityType.SENTINEL | EntityType.GUNNER | EntityType.LAUNCHER:
                    bp = ct.get_position(bid)
                    dist = self.my_pos.distance_squared(bp)
                    if dist < best_dist:
                        best_dist = dist
                        best_dir = self.my_pos.direction_to(bp)
        if best_dir is not None and ct.can_rotate(best_dir):
            ct.rotate(best_dir)
            return True
        return False

    def is_fed(self, ct: Controller) -> bool:
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != self.my_team:
                continue
            match ct.get_entity_type(bid):
                case EntityType.CONVEYOR:
                    if ct.get_position(bid).add(ct.get_direction(bid)) == self.my_pos:
                        return True
                case EntityType.BRIDGE:
                    if ct.get_bridge_target(bid) == self.my_pos:
                        return True
        return False

    def try_self_destruct(self, ct: Controller) -> None:
        has_ally = False
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == self.my_team:
                has_ally = True
            else:
                return
        if has_ally:
            ct.self_destruct()
