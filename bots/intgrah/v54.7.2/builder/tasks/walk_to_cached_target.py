from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingLauncher

from builder.helpers import make_move
from builder.tasks.offense_helpers import vulnerable_harvesters
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedHarvesterInSightError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "a vulnerable harvester is in vision — approach it first"


class TaskRejectedNoCachedTargetError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "offense_target is None"


def walk_to_cached_target(self: Builder, ct: Controller) -> None:
    # The original's "elif offense_target and offense_launcher ..."
    # only runs when vulnerable_harvesters is empty.
    if vulnerable_harvesters(self):
        raise TaskRejectedHarvesterInSightError
    if self.offense_target is None:
        raise TaskRejectedNoCachedTargetError

    if (
        self.offense_launcher
        and isinstance(
            rl := self.get_building(self.offense_launcher),
            BuildingLauncher,
        )
        and rl.team == self.my_team
        and self.my_pos.distance_squared(self.offense_target) > 8
    ):
        make_move(self, ct, self.offense_launcher)
    else:
        make_move(self, ct, self.offense_target)
