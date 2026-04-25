"""Late-game defensive patrol: only fires when at least one friendly
harvester is in vision (otherwise there's nothing to defend nearby).
Lower priority than `patrol_cheap` in the DEFENSE policy — the cheap
variant gates on "broke", this one gates on "have something to guard".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.patrol import run_patrol
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoHarvesterNearbyError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no friendly harvester-adjacent tile in view"


class TaskRejectedPatrolFailedError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "run_patrol produced no action"


def patrol_late(self: Builder, ct: Controller) -> None:
    if not self.adjacent_to_harvester:
        raise TaskRejectedNoHarvesterNearbyError
    if not run_patrol(self, ct):
        raise TaskRejectedPatrolFailedError
