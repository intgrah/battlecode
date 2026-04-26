"""Heal a damaged friendly builder bot within action range. Skips
bots standing on a damaged enemy building — those bots are mid-kill
and would lose progress if we patched them up. Bails out under the
"fight to death" gate (low-HP self on enemy tile)."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.helpers import try_heal
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


class TaskRejectedNoAdjacentBuilderError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no damaged friendly bot in heal range"


def heal_adjacent_builder(self: Builder, ct: Controller) -> None:
    if fight_to_death(self, ct):
        raise TaskRejectedFightToDeathError
    adjacent_builders = ct.get_nearby_units(2)
    for eid in adjacent_builders:
        if (ct.get_hp(eid) <= ct.get_max_hp(eid) - 4) and ct.get_team(
            eid,
        ) == self.my_team:
            position = ct.get_position(eid)
            if has_wounded_enemy(self, position):
                continue
            if try_heal(self, ct, position, conserve_ti=False):
                return
    raise TaskRejectedNoAdjacentBuilderError
