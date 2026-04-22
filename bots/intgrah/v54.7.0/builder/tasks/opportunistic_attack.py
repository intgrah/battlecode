from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNotOpportunistic(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "builder is not in opportunistic mode"


class TaskRejectedRngDeclined(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "random gate (p=0.2) declined"


class TaskRejectedTooEarly(TaskRejectedError):
    def __init__(self, round_: int) -> None:
        self.round = round_

    @override
    def __str__(self) -> str:
        return f"round {self.round} <= 100"


class TaskRejectedCannotFire(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "ct.can_fire(my_pos) is False"


class TaskRejectedFriendlyTile(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "tile under builder holds a friendly building"


def opportunistic_attack(self: Builder, ct: Controller) -> None:
    if not self.opportunistic:
        raise TaskRejectedNotOpportunistic
    if self.rng.random() >= 0.2:
        raise TaskRejectedRngDeclined
    if self.round <= 100:
        raise TaskRejectedTooEarly(self.round)
    if not ct.can_fire(self.my_pos):
        raise TaskRejectedCannotFire
    if ct.get_team(ct.get_tile_building_id(self.my_pos)) == self.my_team:
        raise TaskRejectedFriendlyTile
    ct.fire(self.my_pos)
