from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, EntityType, Position
from util import DELTA_TO_DIR, DIR8

from .helpers import make_move, move_random, try_heal

if TYPE_CHECKING:
    from builder import Builder, PosInt


def _count_visible_attackers(ct: Controller, my_team, target: Position) -> int:
    """Count enemy builder bots currently in attack range of `target`
    (builder bots fire at their own tile, so anyone within 1 king-step
    of target is potentially dealing 2 dmg/turn to it).

    Bounds guards are load-bearing — same OOB crash mode as
    `_enemy_healer_near` in task_attack.
    """
    n = 0
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in DIR8:
        p = target.add(DELTA_TO_DIR[d])
        if not (0 <= p.x < w and 0 <= p.y < h):
            continue
        if ct.is_in_vision(p):
            uid = ct.get_tile_builder_bot_id(p)
            if uid is not None and ct.get_team(uid) != my_team:
                n += 1
    if 0 <= target.x < w and 0 <= target.y < h and ct.is_in_vision(target):
        uid = ct.get_tile_builder_bot_id(target)
        if uid is not None and ct.get_team(uid) != my_team:
            n += 1
    return n


def chebyshev(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _deconflict_rank(
    ct: Controller, my_team, my_id: int, my_pos: Position, target: Position
) -> int:
    """Count visible friendly builder bots with STRICT priority to
    heal `target` over us — strictly closer by chebyshev, or tied
    with a smaller id. Every bot running this with the same visible
    self gets the same answer, so the top-N closest consistently
    commit and the rest defer."""
    my_d = chebyshev(my_pos, target)
    rank = 0
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        fp = ct.get_position(uid)
        fd = chebyshev(fp, target)
        if fd < my_d or (fd == my_d and uid < my_id):
            rank += 1
    return rank


def _healers_needed(attackers: int) -> int:
    """Healers required to outpace `attackers` hitting a single tile.
    Attackers deal 2 dmg/turn each, healers restore 4 hp/turn each,
    so break-even is ceil(attackers/2). Always at least 1 — one bot
    still comes for chip damage even with no visible attacker."""
    if attackers <= 1:
        return 1
    return (attackers + 1) // 2


def best_healable_building(self: Builder, ct: Controller) -> PosInt:
    """Pick the most valuable reachable damaged friendly building with
    attacker-aware deconfliction and priority for harvester-adjacent
    infrastructure.

    Deconfliction: each bot ranks itself by chebyshev distance against
    visible friendly builders; only the top-`ceil(attackers/2)` closest
    commit to a target. Others defer to handle a different target.

    Tier structure:
      3 — harvester-adjacent tile, ANY damage, reachable in time
      2 — ordinary damaged building ≥4 HP missing, reachable
      1 — ordinary damaged building ≥4 HP missing, NOT reachable
      0 — minor chip damage on a non-critical tile

    Reach time = chebyshev - 1 (heal range is r²≤2; we only need to
    get adjacent, not on the tile).
    """
    best: PosInt = -1
    best_score: tuple[int, int, int] = (0, 0, 0)
    my_pos = self.my_pos
    my_id = self.my_id
    my_team = self.my_team
    for pos in self.healable_buildings:
        i = pos
        hp = self.hp[i]
        max_hp = self.max_hp[i]
        damage = max_hp - hp
        if damage <= 0:
            continue

        attackers = _count_visible_attackers(ct, my_team, self.pos(pos))
        needed = _healers_needed(attackers)
        rank = _deconflict_rank(ct, my_team, my_id, self.pos(my_pos), self.pos(pos))
        if rank >= needed:
            if not ct.is_in_vision(self.pos(pos)):
                self.hp[i] = max_hp
            continue

        dist = self.cv_dist(my_pos, pos)
        turns_to_reach = max(0, dist - 1)
        dmg_per_turn = max(2, attackers * 2)
        turns_to_die = max(1, hp // dmg_per_turn)
        # Allow 1 turn of slippage: even after the tile dies, a single
        # enemy attacker needs turns to fire+destroy+rebuild, so we
        # can still slot in a replacement tile. Multiple attackers
        # overwhelm this, but attackers scales dmg_per_turn above.
        can_reach = turns_to_reach <= turns_to_die + 1
        is_critical = pos in self.adjacent_to_harvester

        if is_critical and can_reach:
            tier = 3
        elif damage >= 4 and can_reach:
            tier = 2
        elif damage >= 4:
            tier = 1
        else:
            tier = 0
        score = (tier, damage, turns_to_die - turns_to_reach)

        if score > best_score:
            best = pos
            best_score = score
    self.healable_buildings = [
        p for p in self.healable_buildings if self.hp[p] < self.max_hp[p]
    ]
    return best


def best_adjacent_healable_building(
    self: Builder, tile: PosInt
) -> tuple[PosInt, tuple[int, int]]:
    best: PosInt = -1
    best_score: tuple[int, int] = (0, 0)
    for i in self.healable_buildings:
        if self.sq_dist(tile, i) > 2:
            continue
        hp = self.hp[i]
        max_hp = self.max_hp[i]
        damage = max_hp - hp
        score = (0, damage) if damage < 4 else (1, damage)
        if score > best_score:
            best = i
            best_score = score
    return best, best_score


def healable_all_dirs(self: Builder, tile: PosInt) -> tuple[PosInt, tuple[int, int]]:

    best_spot, best_score = best_adjacent_healable_building(self, tile)
    total_a, total_b = best_score

    for d in DIR8:
        adj = tile + d
        spot, score = best_adjacent_healable_building(self, adj)
        score_a, score_b = score
        total_a += score_a
        total_b += score_b
        if score > best_score:
            best_score = score
            best_spot = spot

    return best_spot, (total_a, total_b)


def best_heal_move_dir(
    self: Builder, ct: Controller
) -> tuple[int, PosInt, tuple[int, int]]:
    my_pos = self.my_pos
    best_dir = 0
    best_spot, best_score = healable_all_dirs(self, my_pos)
    for d in DIR8:
        if not ct.can_move(DELTA_TO_DIR[d]):
            continue
        tile = my_pos + d
        spot, score = healable_all_dirs(self, tile)
        if score > best_score:
            best_score = score
            best_spot = spot
            best_dir = d
    return best_dir, best_spot, best_score


def run_heal(self: Builder, ct: Controller) -> bool:

    if self.repair_pos >= 0 and ct.is_in_vision(self.pos(self.repair_pos)):
        ti = self.repair_pos
        b = self.get_building(ti)
        if b and self.hp[ti] < self.max_hp[ti] - 2 and b.team == self.my_team:
            pass
        else:
            self.repair_pos = -1

    repair_pos = best_healable_building(self, ct)
    if (repair_pos >= 0 and self.my_sq_dist(repair_pos) <= 2) or self.repair_pos < 0:
        self.repair_pos = repair_pos

    being_attacked = False
    if self.repair_pos >= 0:
        heal_position = self.repair_pos
        if ct.is_in_vision(self.pos(heal_position)):
            builder = ct.get_tile_builder_bot_id(self.pos(heal_position))
            being_attacked = (
                builder is not None and ct.get_team(builder) != self.my_team
            )

    save_money = being_attacked and self.repaired_prev

    for tile in ct.get_nearby_tiles(8):
        i = self._idx(tile)
        if self.hp[i] < self.max_hp[i]:
            move_dir, heal_spot, heal_score = best_heal_move_dir(self, ct)
            heal_score = heal_score[1]
            break
    else:
        heal_score = 0
        move_dir = 0
        heal_spot = self.my_pos

    if heal_score == 0:
        if self.repair_pos < 0:
            return False
        make_move(self, ct, self.repair_pos)
        return True
    if move_dir != 0:
        ct.move(DELTA_TO_DIR[move_dir])
        self.my_pos = self.my_pos + move_dir

    if heal_spot:
        ct.draw_indicator_dot(self.pos(heal_spot), 255, 0, 0)
        print(heal_spot, heal_score)
        self.repaired_prev |= try_heal(
            self, ct, heal_spot, conserve_ti=save_money, heal_score=heal_score
        )
    else:
        self.repaired_prev = False

    return True


def has_wounded_enemy(self: Builder, ct: Controller, position: PosInt) -> bool:
    b = self.get_building(position)
    if not b:
        return False
    return b.team != self.my_team and self.hp[position] < self.max_hp[position]


def heal_adjacent_builders(self: Builder, ct: Controller) -> bool:
    adjacent_builders = ct.get_nearby_units(2)
    for eid in adjacent_builders:
        if (ct.get_hp(eid) <= ct.get_max_hp(eid) - 4) and ct.get_team(
            eid
        ) == self.my_team:
            position = ct.get_position(eid)
            if has_wounded_enemy(self, ct, self._idx(position)):
                continue
            if try_heal(self, ct, self._idx(position), conserve_ti=False):
                return True
    return False


def heal_self(self: Builder, ct: Controller) -> bool:
    if ct.get_hp() > ct.get_max_hp() - 4:
        return False

    my_pos = self.my_pos
    if not has_wounded_enemy(self, ct, my_pos):
        try_heal(self, ct, my_pos, conserve_ti=False)
        move_random(self, ct)
        return True

    for d in DIR8:
        if ct.can_move(DELTA_TO_DIR[d]) and not has_wounded_enemy(self, ct, my_pos + d):
            ct.move(DELTA_TO_DIR[d])
            self.my_pos = self.my_pos + d
            try_heal(self, ct, self.my_pos, conserve_ti=False)
            return True

    return False


def heal_builders(self: Builder, ct: Controller) -> bool:
    i = self.my_pos
    b = self.get_building(i)
    if b and b.team != self.my_team:
        if self.hp[i] <= 2:
            return False
        if self.hp[i] <= 6 and ct.get_hp() > 18:
            return False
    return bool(heal_adjacent_builders(self, ct) or heal_self(self, ct))
