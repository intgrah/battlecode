"""Heal a damaged friendly building. Picks a `repair_pos` (committed
target) via `_best_healable_building`'s deconflicted scoring, walks
toward it, and tries `try_heal` on the best in-range tile both before
and after the move. Mutates `self.repair_pos` and `self.repaired_prev`
for cross-turn continuity. Buildings have explicit movement; bot-heal
leaves do not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from util.metrics import chebyshev

from builder.helpers import make_move, try_heal
from builder.tasks.rejected import Reason, TaskRejectedError
from builder.tasks.shared.heal._helpers import (
    count_visible_attackers,
    deconflict_rank,
    healers_needed,
)

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoBuildingToHealError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no damaged friendly building worth healing right now"


def _best_healable_building(self: Builder, ct: Controller) -> Position | None:
    """Pick the most valuable reachable damaged friendly building with
    attacker-aware deconfliction and priority for harvester-adjacent
    infrastructure.

    Deconfliction: each bot ranks itself by chebyshev distance against
    visible friendly builders; only the top-`ceil(attackers/2)` closest
    commit to a target. Others defer to handle a different target.

    Tier structure:
      3 — harvester-adjacent tile, ANY damage, reachable in time
      2 — ordinary damaged building >=4 HP missing, reachable
      1 — ordinary damaged building >=4 HP missing, NOT reachable
      0 — minor chip damage on a non-critical tile

    Reach time = chebyshev - 1 (heal range is r²<=2; we only need to
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

        attackers = count_visible_attackers(self, pos)
        needed = healers_needed(attackers)
        rank = deconflict_rank(self, ct, self.my_pos, pos)
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


def _best_adjacent_healable_building(self: Builder) -> Position | None:
    """Damaged friendly building within heal range (d²<=2). Two-tier
    score: prefer 4+-damage tiles over chip damage; within each tier,
    prefer larger damage.
    """
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


def heal_buildings(self: Builder, ct: Controller) -> None:
    if self.repair_pos and ct.is_in_vision(self.repair_pos):
        b = self.get_building(self.repair_pos)
        ti = self.idx(self.repair_pos)
        if b and self.hp[ti] < self.max_hp[ti] - 2 and b.team == self.my_team:
            pass
        else:
            self.repair_pos = None
    repair_pos = _best_healable_building(self, ct)
    if (
        repair_pos and repair_pos.distance_squared(self.my_pos) <= 2
    ) or not self.repair_pos:
        self.repair_pos = repair_pos

    if not self.repair_pos:
        raise TaskRejectedNoBuildingToHealError

    heal_position = self.repair_pos
    being_attacked = heal_position in self.enemy_bots

    building_to_heal = _best_adjacent_healable_building(self)
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
    building_to_heal = _best_adjacent_healable_building(self)
    if building_to_heal:
        self.repaired_prev = (
            try_heal(self, ct, building_to_heal, conserve_ti=save_money)
            or self.repaired_prev
        )
