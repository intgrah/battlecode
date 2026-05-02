from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Controller, EntityType
from unit import Unit
from util import DIR8

if TYPE_CHECKING:
    from cambc import Direction, Position, Team

__all__ = ["Gunner"]

_SELF_DESTRUCT_THRESHOLD: int = 10
# Gunner attack r²=13 → cardinal range 3 tiles, diagonal range 2 tiles.
_GUNNER_R2: int = 13


def _ray_walk_via_roads(
    ct: Controller,
    start: Position,
    direction: Direction,
    my_team: Team,
) -> tuple[Position, bool, EntityType | None] | None:
    """Walk forward ray from `start` in `direction` up to gunner range.

    Friendly markers and friendly roads are bypassable — markers don't block
    LoS in the engine, and roads are cheap collateral we accept destroying
    to unblock the path. Anything else friendly stops the walk and returns
    None (don't shoot through your own gunner / bot / conveyor / etc.).

    Returns `(pos, is_bot, building_type)` for the first enemy hit on the
    ray, where `is_bot` distinguishes builder bot from building, and
    `building_type` is the EntityType for buildings (None for bots).
    Returns None if no enemy is reachable along this ray.
    """
    cur = start
    for _ in range(3):
        cur = cur.add(direction)
        if cur.distance_squared(start) > _GUNNER_R2:
            return None
        if not ct.is_in_vision(cur):
            return None
        bid = ct.get_tile_building_id(cur)
        if bid is not None:
            btype = ct.get_entity_type(bid)
            if ct.get_team(bid) == my_team:
                if btype != EntityType.MARKER and btype != EntityType.ROAD:
                    return None
                continue
            return (cur, False, btype)
        uid = ct.get_tile_builder_bot_id(cur)
        if uid is not None:
            if ct.get_team(uid) == my_team:
                return None
            return (cur, True, None)
    return None


class Gunner(Unit):
    @override
    def __init__(self, ct: Controller) -> None:
        self.idle_turns: int = 0

    @override
    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        my_id = ct.get_id()
        my_pos = ct.get_position(my_id)
        facing = ct.get_direction(my_id)

        # Rule 1: fire whenever there's a reachable enemy on our facing ray,
        # allowing friendly roads/markers as bypass-able. The engine fires
        # at the first blocker, so if a friendly road sits between us and
        # the enemy we destroy the road this turn and clear the path for
        # next turn's shot.
        target = ct.get_gunner_target()
        if (
            target is not None
            and ct.can_fire(target)
            and _ray_walk_via_roads(ct, my_pos, facing, my_team) is not None
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
        """Rule 2: prefer enemy gunners that can shoot us, then enemy bots.
        Reachability uses the same Rule 1 walk — only friendly roads/markers
        are acceptable in between. Other enemy buildings (sentinels,
        launchers, breaches, infrastructure) are not picked as rotation
        targets here; if one happens to be on our current ray the run-loop
        fire branch will still shoot it.
        """
        my_team = ct.get_team()
        my_pos = ct.get_position()

        best_gunner_dir: Direction | None = None
        best_gunner_dist: int = _GUNNER_R2 + 1
        best_bot_dir: Direction | None = None
        best_bot_dist: int = _GUNNER_R2 + 1

        for d in DIR8:
            result = _ray_walk_via_roads(ct, my_pos, d, my_team)
            if result is None:
                continue
            target_pos, is_bot, btype = result
            dist_sq = my_pos.distance_squared(target_pos)

            if not is_bot and btype == EntityType.GUNNER:
                # By symmetry, an enemy gunner on a length-≤_GUNNER_R2 ray
                # from us is also within its own r²=13 of us, so it can
                # rotate (1-turn cooldown) and shoot us next turn.
                if dist_sq < best_gunner_dist:
                    best_gunner_dist = dist_sq
                    best_gunner_dir = d
            elif is_bot:
                if dist_sq < best_bot_dist:
                    best_bot_dist = dist_sq
                    best_bot_dir = d

        chosen = best_gunner_dir if best_gunner_dir is not None else best_bot_dir
        if chosen is not None and ct.can_rotate(chosen):
            ct.rotate(chosen)
            return True
        return False

    def _try_self_destruct(self, ct: Controller) -> None:
        my_team = ct.get_team()
        has_ally = False
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                has_ally = True
            else:
                return
        if has_ally:
            ct.self_destruct()
