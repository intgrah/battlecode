"""Cheap, low-priority opportunistic fire used by ECON / DEFENSE roles.
A small fraction of builders (`self.opportunistic` set at init) randomly
fire (p=0.2) on the enemy building under their feet, but only after round
100. Distinct from OFFENSE's structured attack cascade — this is just
"if standing on an enemy thing, occasionally hit it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNotOpportunisticError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "builder is not in opportunistic mode"


class TaskRejectedRngDeclinedError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "random gate (p=0.2) declined"


class TaskRejectedTooEarlyError(TaskRejectedError):
    def __init__(self, round_: int) -> None:
        self.round = round_

    @override
    def reason(self) -> Reason:
        return "round {round} <= 100", {"round": self.round}


class TaskRejectedCannotFireError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "ct.can_fire(my_pos) is False"


class TaskRejectedFriendlyTileError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "tile under builder holds a friendly building"


def opportunistic_attack(self: Builder, ct: Controller) -> None:
    if not self.opportunistic:
        raise TaskRejectedNotOpportunisticError
    if self.rng.random() >= 0.2:
        raise TaskRejectedRngDeclinedError
    if self.round <= 100:
        raise TaskRejectedTooEarlyError(self.round)
    if not ct.can_fire(self.my_pos):
        raise TaskRejectedCannotFireError
    if ct.get_team(ct.get_tile_building_id(self.my_pos)) == self.my_team:
        raise TaskRejectedFriendlyTileError
    ct.fire(self.my_pos)
