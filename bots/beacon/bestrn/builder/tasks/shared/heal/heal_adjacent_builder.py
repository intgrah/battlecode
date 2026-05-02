"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/heal_adjacent_builder.py`.

Heal a damaged friendly builder bot within action range. Skips
bots standing on a damaged enemy building — those bots are mid-kill
and would lose progress if we patched them up. Bails out under the
"fight to death" gate (low-HP self on enemy tile).
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import try_heal
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from builder.tasks.shared.heal._helpers import fight_to_death, has_wounded_enemy

def heal_adjacent_builder(self_, ct):
    if fight_to_death(self_, ct):
        return TaskRejected("low HP on enemy tile — fight to death, no heal")
    adjacent_builders = ct.get_nearby_units(2)
    for eid in adjacent_builders:
        if ct.get_hp(eid) <= ct.get_max_hp(eid) - 4 and ct.get_team(eid) == self_.my_team:
            position = ct.get_position(eid)
            if has_wounded_enemy(self_, position):
                continue
            if try_heal(self_, ct, position, False):
                return None
    return TaskRejected("no damaged friendly bot in heal range")
