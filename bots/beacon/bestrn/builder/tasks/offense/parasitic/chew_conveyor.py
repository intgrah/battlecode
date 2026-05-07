"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/parasitic/chew_conveyor.py`.

Fallback offense: with no vulnerable harvester and no cached target,
pick an enemy conveyor/splitter/bridge tile (via `pick_conveyor_target` —
prefers near-enemy-core, then visible-flow tiles, with spacing from our
other attackers) and either fire on it (if standing on it) or walk toward
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move, try_attack
from builder.tasks.offense.helpers import (
    pick_conveyor_target,
    should_attack,
    vulnerable_harvesters,
)
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult


def chew_conveyor(self_, ct):
    if not (not vulnerable_harvesters(self_)):
        return TaskRejected("a vulnerable harvester is in vision — handle that first")
    if self_.offense_target is not None:
        return TaskRejected("offense_target is set — walk_to_cached_target handles it")
    enemy_core = self_.en_core_guess
    my_pos = self_.my_pos
    conveyor_target = pick_conveyor_target(self_, ct, enemy_core, my_pos)
    conveyor_target = conveyor_target
    if conveyor_target is None:
        return TaskRejected("pick_conveyor_target returned None")
    if my_pos == conveyor_target:
        if should_attack(self_, conveyor_target):
            try_attack(ct, my_pos)
    else:
        make_move(self_, ct, conveyor_target)
    return None
