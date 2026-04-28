"""Fallback offense: with no vulnerable harvester and no cached target,
pick an enemy conveyor/splitter/bridge tile (via `pick_conveyor_target` —
prefers near-enemy-core, then visible-flow tiles, with spacing from our
other attackers) and either fire on it (if standing on it) or walk toward
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.helpers import make_move, try_attack
from builder.tasks.offense.helpers import (
    pick_conveyor_target,
    should_attack,
    vulnerable_harvesters,
)
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedHarvesterInSightError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "a vulnerable harvester is in vision — handle that first"


class TaskRejectedHasCachedTargetError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "offense_target is set — walk_to_cached_target handles it"


class TaskRejectedNoConveyorTargetError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "pick_conveyor_target returned None"


def chew_conveyor(self: Builder, ct: Controller) -> None:
    # Original's else branch runs only when vulnerable_harvesters is
    # empty AND offense_target is None.
    if vulnerable_harvesters(self):
        raise TaskRejectedHarvesterInSightError
    if self.offense_target is not None:
        raise TaskRejectedHasCachedTargetError

    enemy_core = self.en_core_guess
    conveyor_target = pick_conveyor_target(self, ct, enemy_core, self.my_pos)
    if conveyor_target is None:
        raise TaskRejectedNoConveyorTargetError

    if self.my_pos == conveyor_target:
        if should_attack(self, conveyor_target):
            try_attack(ct, self.my_pos)
    else:
        make_move(self, ct, conveyor_target)
