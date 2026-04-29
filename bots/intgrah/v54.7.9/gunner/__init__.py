from __future__ import annotations

from typing import Final, override

from cambc import Controller, Direction, EntityType, GameConstants, Position
from unit import Unit
from util.directions import DIR8

__all__ = ["Gunner"]


class Gunner(Unit):
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
    def __init__(self) -> None:
        super().__init__()
        self.idle_turns: int = 0

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)

        facing = ct.get_direction()
        fire_target = self._fire_target(ct, facing)
        if fire_target is not None and ct.can_fire(fire_target):
            ct.fire(fire_target)
            self.idle_turns = 0
            return

        if self.try_rotate_to_enemy(ct):
            self.idle_turns = 0
        else:
            self.idle_turns += 1

        if self.idle_turns > Gunner.SELF_DESTRUCT_THRESHOLD:
            self.try_self_destruct(ct)

    def _fire_target(self, ct: Controller, direction: Direction) -> Position | None:
        """Walk the forward ray. Return the first blocker iff firing
        actually damages the enemy: enemy non-harvester building OR
        enemy bot. A friendly absorber (any of our buildings except a
        marker, or our bot) returns None — the engine shoots the first
        blocker and a friendly one would eat the projectile.
        """
        cur = self.my_pos
        for _ in range(3):
            cur = cur.add(direction)
            if cur.distance_squared(self.my_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                return None
            if not self.in_bounds(cur):
                return None
            if not ct.is_in_vision(cur):
                return None
            bid = ct.get_tile_building_id(cur)
            if bid is not None:
                etype = ct.get_entity_type(bid)
                if etype == EntityType.MARKER:
                    continue
                if ct.get_team(bid) == self.my_team:
                    return None
                if etype == EntityType.HARVESTER:
                    return None
                return cur
            uid = self.all_bots.get(cur)
            if uid is not None:
                if ct.get_team(uid) == self.my_team:
                    return None
                return cur
        return None

    def _score_ray(
        self,
        ct: Controller,
        direction: Direction,
    ) -> tuple[int, Position | None]:
        """Walk the forward ray from `my_pos` in `direction` (3 steps,
        capped by GUNNER_VISION_RADIUS_SQ). Return (score, blocker_pos):

          3 — enemy turret in VALID_ROTATION_TARGETS (highest value)
          2 — enemy builder bot
          1 — enemy core (always-on chip damage; below builders so a
              free builder wins the rotation tiebreak)
          0 — empty ray, friendly absorber, enemy harvester, enemy
              non-target transport (conveyor / road etc.), vision gap

        Markers are transparent. A friendly bot or non-marker friendly
        building scores 0 (would eat our shot). Enemy harvesters score
        0 (15 shots to kill, may feed a chain we're parasitising).
        """
        cur = self.my_pos
        for _ in range(3):
            cur = cur.add(direction)
            if (
                cur.distance_squared(self.my_pos)
                > GameConstants.GUNNER_VISION_RADIUS_SQ
            ):
                return (0, None)
            if not self.in_bounds(cur):
                return (0, None)
            if not ct.is_in_vision(cur):
                return (0, None)
            bid = ct.get_tile_building_id(cur)
            if bid is not None:
                etype = ct.get_entity_type(bid)
                if etype == EntityType.MARKER:
                    continue
                if ct.get_team(bid) == self.my_team:
                    return (0, cur)  # friendly building absorbs
                if etype == EntityType.HARVESTER:
                    return (0, cur)  # enemy harvester: skip
                if etype == EntityType.CORE:
                    return (1, cur)  # enemy core
                if etype not in Gunner.VALID_ROTATION_TARGETS:
                    return (0, cur)  # conveyor / road / etc.
                return (3, cur)  # enemy turret
            uid = self.all_bots.get(cur)
            if uid is not None:
                if ct.get_team(uid) == self.my_team:
                    return (0, cur)  # friendly bot absorbs
                return (2, cur)  # enemy bot
        return (0, None)

    def try_rotate_to_enemy(self, ct: Controller) -> bool:
        """Find a direction whose forward ray hits something worth shooting.
        Enumerates all 8 directions, scores each via the same logic the
        fire decision uses, and picks the highest-scoring direction
        (tiebreak by closest blocker).
        """
        best_score = 0
        best_dist_sq = 999
        best_dir: Direction | None = None
        for d in DIR8:
            score, bpos = self._score_ray(ct, d)
            if score == 0 or bpos is None:
                continue
            dist_sq = self.my_pos.distance_squared(bpos)
            if (score, -dist_sq) > (best_score, -best_dist_sq):
                best_score = score
                best_dist_sq = dist_sq
                best_dir = d
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
