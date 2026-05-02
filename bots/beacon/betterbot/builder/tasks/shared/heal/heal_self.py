"""Heal own tile. If standing on an enemy building, step off first
(otherwise the heal is wasted on the enemy structure too) — but only
when there's an unwounded escape direction. Bails out under the
"fight to death" gate (low-HP self on enemy tile).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import GameConstants

from builder.helpers import move_random, try_heal
from builder.tasks.rejected import Reason, TaskRejectedError
from builder.tasks.shared.heal._helpers import (
    fight_to_death,
    has_wounded_enemy,
)

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedFightToDeathError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "low HP on enemy tile — fight to death, no heal"


class TaskRejectedFullHpError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "self HP within HEAL_AMOUNT of max — heal would waste Ti"


class TaskRejectedNoEscapeError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "on wounded enemy tile, no safe step-off direction"


def heal_self(self: Builder, ct: Controller) -> None:
    if fight_to_death(self, ct):
        raise TaskRejectedFightToDeathError
    if ct.get_hp() > ct.get_max_hp() - GameConstants.HEAL_AMOUNT:
        raise TaskRejectedFullHpError

    if not has_wounded_enemy(self, self.my_pos):
        try_heal(self, ct, self.my_pos, conserve_ti=False)
        move_random(self, ct)
        return

    for d, n in self.dir_neighbours_8:
        if ct.can_move(d) and not has_wounded_enemy(self, n):
            ct.move(d)
            try_heal(self, ct, ct.get_position(), conserve_ti=False)
            return

    raise TaskRejectedNoEscapeError
