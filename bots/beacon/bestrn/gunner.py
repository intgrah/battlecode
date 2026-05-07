"""Translation of `bots/intgrah/v54.7.9/gunner/__init__.py`."""

from __future__ import annotations

from typing import Final

from unit import in_bounds
from cambc import EntityType, GameConstants
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Direction, Position
from unit import UnitState
from util.directions import DIR8


def is_valid_rotation_target(et):
    """
    Valid priority targets for rotation: other enemy turrets we should
    actually use our shot on.
    """
    return (
        et == EntityType.SENTINEL
        or et == EntityType.GUNNER
        or et == EntityType.LAUNCHER
        or et == EntityType.BREACH
    )


class Gunner:
    state: UnitState
    idle_turns: int

    def __init__(self):
        self.state = UnitState()
        self.idle_turns = 0

    SELF_DESTRUCT_THRESHOLD: Final[int] = 10

    def fire_target(self, ct, direction):
        """
        Walk the forward ray. Return the first blocker iff firing
        actually damages the enemy: enemy non-harvester building OR
        enemy bot. A friendly absorber (any of our buildings except a
        marker, or our bot) returns None — the engine shoots the first
        blocker and a friendly one would eat the projectile.
        """
        my_pos = self.state.my_pos
        my_team = self.state.my_team
        cur = my_pos
        for _ in range(0, 3):
            cur = cur.add(direction)
            if cur.distance_squared(my_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ:
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
                if ct.get_team(bid) == my_team:
                    return None
                if etype == EntityType.HARVESTER:
                    return None
                return cur
            uid = self.state.all_bots.get(cur)
            if uid is not None:
                if ct.get_team(uid) == my_team:
                    return None
                return cur
        return None

    def score_ray(self, ct, direction):
        """
        Walk the forward ray from `my_pos` in `direction` (3 steps,
        capped by `GUNNER_VISION_RADIUS_SQ`). Return (score, `blocker_pos)`:

          3 — enemy turret in `VALID_ROTATION_TARGETS` (highest value)
          2 — enemy builder bot
          1 — enemy core (always-on chip damage; below builders so a
              free builder wins the rotation tiebreak)
          0 — empty ray, friendly absorber, enemy harvester, enemy
              non-target transport (conveyor / road etc.), vision gap

        Markers are transparent. A friendly bot or non-marker friendly
        building scores 0 (would eat our shot). Enemy harvesters score
        0 (15 shots to kill, may feed a chain we're parasitising).
        """
        my_pos = self.state.my_pos
        my_team = self.state.my_team
        cur = my_pos
        for _ in range(0, 3):
            cur = cur.add(direction)
            if cur.distance_squared(my_pos) > GameConstants.GUNNER_VISION_RADIUS_SQ:
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
                if ct.get_team(bid) == my_team:
                    return (0, cur)
                if etype == EntityType.HARVESTER:
                    return (0, cur)
                if etype == EntityType.CORE:
                    return (1, cur)
                if not is_valid_rotation_target(etype):
                    return (0, cur)
                return (3, cur)
            uid = self.state.all_bots.get(cur)
            if uid is not None:
                if ct.get_team(uid) == my_team:
                    return (0, cur)
                return (2, cur)
        return (0, None)

    def try_rotate_to_enemy(self, ct):
        """
        Find a direction whose forward ray hits something worth shooting.
        Enumerates all 8 directions, scores each via the same logic the
        fire decision uses, and picks the highest-scoring direction
        (tiebreak by closest blocker).
        """
        best_score: int = 0
        best_dist_sq: int = 999
        best_dir: Direction | None = None
        for d in DIR8:
            score, bpos = self.score_ray(ct, d)
            bpos = bpos
            if bpos is None:
                continue
            if score == 0:
                continue
            dist_sq = self.state.my_pos.distance_squared(bpos)
            if (score, -dist_sq) > (best_score, -best_dist_sq):
                best_score = score
                best_dist_sq = dist_sq
                best_dir = d
        d = best_dir
        if d is not None and (ct.can_rotate(d)):
            ct.rotate(d)
            return True
        return False

    def try_self_destruct(self, ct):
        my_team = self.state.my_team
        has_ally = False
        for uid in ct.get_nearby_units(None):
            if ct.get_team(uid) == my_team:
                has_ally = True
            else:
                return
        if has_ally:
            ct.self_destruct()

    @staticmethod
    def default():
        return Gunner()

    def unit_state(self):
        return self.state

    def unit_state_mut(self):
        return self.state

    def run(self, ct):
        self.state.cache_per_turn_state(ct)
        self.state.check_symmetry_marker(ct)
        facing = ct.get_direction(None)
        fire_target = self.fire_target(ct, facing)
        target = fire_target
        if target is not None and (ct.can_fire(target)):
            ct.fire(target)
            self.idle_turns = 0
            return
        if self.try_rotate_to_enemy(ct):
            self.idle_turns = 0
        else:
            self.idle_turns += 1
        if self.idle_turns > Gunner.SELF_DESTRUCT_THRESHOLD:
            self.try_self_destruct(ct)

    def post_init(self, ct):
        """
        ct-dependent init. Runs once on first turn for this unit. Mirrors
        Python `Unit.post_init`.
        """
        s = self.unit_state_mut()
        s.init_static_state(ct)
        s.narrow_symmetry_from_vision(ct)

    def idx(self, pos):
        """
        Position to flat index. Stride is `MAX_WIDTH=50` regardless of actual
        map size.
        """
        return int(pos.y) * 50 + int(pos.x)

    def in_bounds(self, pos):
        """Is in bounds of the actual map."""
        s = self.unit_state()
        return in_bounds(pos, s.width, s.height)
