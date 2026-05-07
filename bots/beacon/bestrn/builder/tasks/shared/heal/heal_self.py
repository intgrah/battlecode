"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/heal_self.py`.

Heal own tile. If standing on an enemy building, step off first
(otherwise the heal is wasted on the enemy structure too) — but only
when there's an unwounded escape direction. Bails out under the
"fight to death" gate (low-HP self on enemy tile).
"""

from __future__ import annotations

from cambc import GameConstants

from builder.helpers import move_random, try_heal
from builder.tasks.rejected import TaskRejected
from builder.tasks.shared.heal._helpers import fight_to_death, has_wounded_enemy


def heal_self(self_, ct):
    if fight_to_death(self_, ct):
        return TaskRejected("low HP on enemy tile — fight to death, no heal")
    if ct.get_hp(None) > ct.get_max_hp(None) - GameConstants.HEAL_AMOUNT:
        return TaskRejected("self HP within HEAL_AMOUNT of max — heal would waste Ti")
    my_pos = self_.my_pos
    if not has_wounded_enemy(self_, my_pos):
        try_heal(self_, ct, my_pos, False)
        move_random(self_, ct)
        return None
    dir_neighbours_8 = list(self_.dir_neighbours_8)
    for d, n in dir_neighbours_8:
        if ct.can_move(d) and not has_wounded_enemy(self_, n):
            ct.move(d)
            cur = ct.get_position(None)
            try_heal(self_, ct, cur, False)
            return None
    return TaskRejected("on wounded enemy tile, no safe step-off direction")
