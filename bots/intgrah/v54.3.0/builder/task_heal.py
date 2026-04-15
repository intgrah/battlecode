from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, EntityType, Position
from util import DIR8, chebyshev

from builder.helpers import make_move, move_random, try_heal

if TYPE_CHECKING:
    from builder import Builder


def _count_visible_attackers(self: Builder, target: Position) -> int:
    """Count enemy builder bots currently in attack range of `target`
    (builder bots fire at their own tile, so anyone within 1 king-step
    of target is potentially dealing 2 dmg/turn to it).

    Bounds guards are load-bearing — same OOB crash mode as
    `_enemy_healer_near` in task_attack.
    """
    return sum(1 for p in self.enemy_bots if p.distance_squared(target) <= 2)


def _deconflict_rank(
    self: Builder,
    ct: Controller,
    my_pos: Position,
    target: Position,
) -> int:
    """Count visible friendly builder bots with STRICT priority to
    heal `target` over us — strictly closer by chebyshev, or tied
    with a smaller id. Every bot running this with the same visible
    self gets the same answer, so the top-N closest consistently
    commit and the rest defer.
    """
    my_d = chebyshev(my_pos, target)
    rank = 0
    for uid in ct.get_nearby_units():
        if uid == self.my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != self.my_team:
            continue
        fp = ct.get_position(uid)
        fd = chebyshev(fp, target)
        if fd < my_d or (fd == my_d and uid < self.my_id):
            rank += 1
    return rank


def _healers_needed(attackers: int) -> int:
    """Healers required to outpace `attackers` hitting a single tile.
    Attackers deal 2 dmg/turn each, healers restore 4 hp/turn each,
    so break-even is ceil(attackers/2). Always at least 1 — one bot
    still comes for chip damage even with no visible attacker.
    """
    if attackers <= 1:
        return 1
    return (attackers + 1) // 2


def best_healable_building(self: Builder, ct: Controller) -> Position | None:
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
    best: Position | None = None
    best_score: tuple[int, int, int] = (0, 0, 0)
    for pos in self.healable_buildings:
        i = self.idx(pos)
        hp = self.hp[i]
        max_hp = self.max_hp[i]
        damage = max_hp - hp
        if damage <= 0:
            continue

        attackers = _count_visible_attackers(self, pos)
        needed = _healers_needed(attackers)
        rank = _deconflict_rank(self, ct, self.my_pos, pos)
        if rank >= needed:
            if not ct.is_in_vision(pos):
                self.hp[i] = max_hp
            continue

        dist = chebyshev(self.my_pos, pos)
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
        p
        for p in self.healable_buildings
        if self.hp[self.idx(p)] < self.max_hp[self.idx(p)]
    ]
    return best


def best_adjacent_healable_building(self: Builder) -> Position | None:
    best: Position | None = None
    best_score: tuple[int, int] = (0, 0)
    for pos in self.healable_buildings:
        i = self.idx(pos)
        hp = self.hp[i]
        max_hp = self.max_hp[i]
        damage = max_hp - hp
        if self.my_pos.distance_squared(pos) > 2:
            continue
        score = (0, damage) if damage < 4 else (1, damage)
        if score > best_score:
            best = pos
            best_score = score
    return best


def run_heal(self: Builder, ct: Controller) -> bool:
    if self.repair_pos and ct.is_in_vision(self.repair_pos):
        b = self.get_building(self.repair_pos)
        ti = self.idx(self.repair_pos)
        if b and self.hp[ti] < self.max_hp[ti] - 2 and b.team == self.my_team:
            pass
        else:
            self.repair_pos = None
    repair_pos = best_healable_building(self, ct)
    if (
        repair_pos and repair_pos.distance_squared(self.my_pos) <= 2
    ) or not self.repair_pos:
        self.repair_pos = repair_pos

    if not self.repair_pos:
        return False

    heal_position = self.repair_pos
    being_attacked = heal_position in self.enemy_bots

    building_to_heal = best_adjacent_healable_building(self)
    save_money = being_attacked and self.repaired_prev
    if building_to_heal:
        self.repaired_prev = try_heal(
            self,
            ct,
            building_to_heal,
            conserve_ti=save_money,
        )
    else:
        self.repaired_prev = False
    make_move(self, ct, self.repair_pos)
    building_to_heal = best_adjacent_healable_building(self)
    if building_to_heal:
        self.repaired_prev = (
            try_heal(self, ct, building_to_heal, conserve_ti=save_money)
            or self.repaired_prev
        )
    return True


def has_wounded_enemy(self: Builder, position: Position) -> bool:
    b = self.get_building(position)
    if not b:
        return False
    i = self.idx(position)
    return b.team != self.my_team and self.hp[i] < self.max_hp[i]


def heal_adjacent_builders(self: Builder, ct: Controller) -> bool:
    adjacent_builders = ct.get_nearby_units(2)
    for eid in adjacent_builders:
        if (ct.get_hp(eid) <= ct.get_max_hp(eid) - 4) and ct.get_team(
            eid,
        ) == self.my_team:
            position = ct.get_position(eid)
            if has_wounded_enemy(self, position):
                continue
            if try_heal(self, ct, position, conserve_ti=False):
                return True
    return False


def heal_self(self: Builder, ct: Controller) -> bool:
    if ct.get_hp() > ct.get_max_hp() - 4:
        return False

    if not has_wounded_enemy(self, self.my_pos):
        try_heal(self, ct, self.my_pos, conserve_ti=False)
        move_random(self, ct)
        return True

    for d in DIR8:
        if ct.can_move(d) and not has_wounded_enemy(self, self.my_pos.add(d)):
            ct.move(d)
            try_heal(self, ct, ct.get_position(), conserve_ti=False)
            return True

    return False


def heal_builders(self: Builder, ct: Controller) -> bool:
    b = self.get_building(self.my_pos)
    if b and b.team != self.my_team:
        i = self.idx(self.my_pos)
        if self.hp[i] <= 2:
            return False
        if self.hp[i] <= 6 and ct.get_hp() > 18:
            return False
    return bool(heal_adjacent_builders(self, ct) or heal_self(self, ct))
