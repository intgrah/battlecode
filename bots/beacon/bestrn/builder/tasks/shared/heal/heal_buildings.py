"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/heal_buildings.py`.

Heal a damaged friendly building. Picks a `repair_pos` (committed
target) via `_best_healable_building`'s deconflicted scoring, walks
toward it, and tries `try_heal` on the best in-range tile both before
and after the move. Mutates `self.repair_pos` and `self.repaired_prev`
for cross-turn continuity. Buildings have explicit movement; bot-heal
leaves do not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move, try_heal
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from builder.tasks.shared.heal._helpers import (
    count_visible_attackers,
    deconflict_rank,
    healers_needed,
)
from util.metrics import chebyshev


def best_healable_building(self_, ct):
    """
    Pick the most valuable reachable damaged friendly building with
    attacker-aware deconfliction and priority for harvester-adjacent
    infrastructure.
    """
    best: Position | None = None
    best_score: tuple[int, int, int] = (0, 0, 0)
    healable = list(self_.healable_buildings)
    for pos in healable:
        i = self_.idx(pos)
        hp = self_.hp[i]
        max_hp = self_.max_hp[i]
        damage = max_hp - hp
        if damage <= 0:
            continue
        attackers = count_visible_attackers(self_, pos)
        needed = healers_needed(attackers)
        rank = deconflict_rank(self_, ct, self_.my_pos, pos)
        if rank >= needed:
            if not ct.is_in_vision(pos):
                self_.hp[i] = max_hp
            continue
        dist = chebyshev(self_.my_pos, pos)
        turns_to_reach = max(dist - 1, 0)
        dmg_per_turn = max(attackers * 2, 2)
        turns_to_die = max(hp // dmg_per_turn, 1)
        can_reach = turns_to_reach <= turns_to_die + 1
        is_critical = pos in self_.adjacent_to_harvester
        tier = (
            3
            if is_critical and can_reach
            else (2 if damage >= 4 and can_reach else int(damage >= 4))
        )
        score = (tier, damage, turns_to_die - turns_to_reach)
        if score > best_score:
            best = pos
            best_score = score
    self_.healable_buildings = list(
        (
            p
            for p in self_.healable_buildings
            if self_.hp[self_.idx(p)] < self_.max_hp[self_.idx(p)]
        )
    )
    return best


def best_adjacent_healable_building(self_):
    """
    Damaged friendly building within heal range (d²<=2). Two-tier
    score: prefer 4+-damage tiles over chip damage; within each tier,
    prefer larger damage.
    """
    best: Position | None = None
    best_score: tuple[int, int] = (0, 0)
    for pos in self_.healable_buildings:
        i = self_.idx(pos)
        hp = self_.hp[i]
        max_hp = self_.max_hp[i]
        damage = max_hp - hp
        if self_.my_pos.distance_squared(pos) > 2:
            continue
        score = (0, damage) if damage < 4 else (1, damage)
        if score > best_score:
            best = pos
            best_score = score
    return best


def heal_buildings(self_, ct):
    rp = self_.repair_pos
    if rp is not None and (ct.is_in_vision(rp)):
        ti_idx = self_.idx(rp)
        __opt__kind_team = self_.get_building(rp)
        _kind = __opt__kind_team[0] if __opt__kind_team is not None else None
        team = __opt__kind_team[1] if __opt__kind_team is not None else None
        if (
            __opt__kind_team is not None
            and (self_.hp[ti_idx] < self_.max_hp[ti_idx] - 2)
            and (team == self_.my_team)
        ):
            pass
        else:
            self_.repair_pos = None
    new_repair = best_healable_building(self_, ct)
    if (
        (new_repair is not None)
        and new_repair.distance_squared(self_.my_pos) <= 2
        or (self_.repair_pos is None)
    ):
        self_.repair_pos = new_repair
    repair_pos = self_.repair_pos
    if repair_pos is None:
        return TaskRejected("no damaged friendly building worth healing right now")
    heal_position = repair_pos
    being_attacked = heal_position in self_.enemy_bots
    building_to_heal = best_adjacent_healable_building(self_)
    save_money = being_attacked and self_.repaired_prev
    bpos = building_to_heal
    if bpos is not None:
        self_.repaired_prev = try_heal(self_, ct, bpos, save_money)
    else:
        self_.repaired_prev = False
    make_move(self_, ct, heal_position)
    building_to_heal = best_adjacent_healable_building(self_)
    bpos = building_to_heal
    if bpos is not None:
        self_.repaired_prev = (
            try_heal(self_, ct, bpos, save_money) or self_.repaired_prev
        )
    return None
