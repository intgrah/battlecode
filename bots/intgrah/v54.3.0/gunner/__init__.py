from __future__ import annotations

from typing import Final, override

from cambc import Controller, Direction, EntityType, GameConstants, Position
from unit import StationaryUnit
from util import DIR8

__all__ = ["Gunner"]


class Gunner(StationaryUnit):
    SELF_DESTRUCT_THRESHOLD: Final[int] = 10

    VALID_ROTATION_TARGETS: Final[frozenset[EntityType]] = frozenset(
        {
            EntityType.SENTINEL,
            EntityType.GUNNER,
            EntityType.LAUNCHER,
            EntityType.BREACH,
        },
    )
    """
    Valid priority targets for rotation: other enemy turrets we should
    actually use our shot on.
    """

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
            # Never shoot enemy harvesters with gunners: 30 HP = 15
            # shots to kill, not cost-effective, and the harvester
            # might be upstream of a chain we're parasitizing — if
            # we've tapped their belt for our own feed, killing the
            # source takes us with it. Let builder bots deal with
            # harvesters.
            is_enemy_harvester = (
                is_enemy_building and ct.get_entity_type(bid) == EntityType.HARVESTER
            )
            if (
                not is_friendly
                and not is_enemy_harvester
                and (is_enemy_building or is_enemy_bot)
                and self.firing_path_clear(ct)
            ):
                ct.fire(target)
                self.idle_turns = 0
                return

        if self.try_rotate_to_enemy(ct):
            self.idle_turns = 0
        else:
            self.idle_turns += 1

        if self.idle_turns > Gunner.SELF_DESTRUCT_THRESHOLD:
            self.try_self_destruct(ct)

    def walk_ray(
        self,
        ct: Controller,
        direction: Direction,
    ) -> tuple[Position, int | None, int | None] | None:
        """Walk the gunner's forward ray from `start` in `direction`. Stop
        at the first occupant (non-marker building, or builder bot), or
        when r²>13, or when a tile leaves our vision. Return
        `(position, building_id, unit_id)` for the blocker, or None if the
        ray was empty / out-of-vision with no blocker seen.
        """
        cur = self.my_pos
        for _ in range(3):
            cur = cur.add(direction)
            if (
                cur.distance_squared(self.my_pos)
                > GameConstants.GUNNER_VISION_RADIUS_SQ
            ):
                return None
            if not self.in_bounds(cur):
                return None
            if not ct.is_in_vision(cur):
                return None
            bid = ct.get_tile_building_id(cur)
            if bid is not None and ct.get_entity_type(bid) != EntityType.MARKER:
                return (cur, bid, None)
            uid = ct.get_tile_builder_bot_id(cur)
            if uid is not None:
                return (cur, None, uid)
        return None

    def firing_path_clear(self, ct: Controller) -> bool:
        """Trace along our facing ray. Return False if any friendly bot or
        non-marker friendly building would absorb our shot first. The
        engine fires at the FIRST blocker in the ray, friend or foe, so a
        friendly sentinel sitting in the line of fire eats the projectile
        before it reaches the enemy we were aiming at.
        """
        facing = ct.get_direction()
        cur = self.my_pos
        for _ in range(3):
            cur = cur.add(facing)
            if (
                cur.distance_squared(self.my_pos)
                > GameConstants.GUNNER_VISION_RADIUS_SQ
            ):
                return True
            bid = ct.get_tile_building_id(cur)
            if bid is not None:
                if ct.get_team(bid) == self.my_team:
                    if ct.get_entity_type(bid) != EntityType.MARKER:
                        return False
                else:
                    return True
            uid = ct.get_tile_builder_bot_id(cur)
            if uid is not None:
                return ct.get_team(uid) != self.my_team
        return True

    def try_rotate_to_enemy(self, ct: Controller) -> bool:
        """Find a direction whose forward ray *actually hits* something
        worth shooting. Enumerates all 8 directions and walks each ray
        to its first blocker, then scores by target type. This fixes
        the bug where the old logic would rotate toward an enemy turret
        that sits behind a harvester / wall / friendly building — the
        shot would hit the blocker instead of the intended target.
        """
        best_score = -1
        best_dist_sq = 999
        best_dir: Direction | None = None
        for direction in DIR8:
            blocker = self.walk_ray(ct, direction)
            if blocker is None:
                continue
            bpos, bid, uid = blocker
            if bid is not None:
                if ct.get_team(bid) == self.my_team:
                    continue
                etype = ct.get_entity_type(bid)
                if etype not in Gunner.VALID_ROTATION_TARGETS:
                    # Enemy harvester / conveyor / road / core etc. —
                    # not worth a gunner shot, and may be parasitized.
                    continue
                score = 2
            elif uid is not None:
                if ct.get_team(uid) == self.my_team:
                    continue
                score = 1  # enemy bot — valid but lower priority
            else:
                continue
            dist_sq = self.my_pos.distance_squared(bpos)
            if (score, -dist_sq) > (best_score, -best_dist_sq):
                best_score = score
                best_dist_sq = dist_sq
                best_dir = direction
        if best_dir is not None and ct.can_rotate(best_dir):
            ct.rotate(best_dir)
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
