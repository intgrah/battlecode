"""Walk a defensive route around our economy, but only when we can't
afford a harvester (otherwise the Ti is better spent on another harvester
build). Used by DEFENSE role early-game when funds are tight; later the
late-patrol variant takes over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType

from builder.helpers import can_afford
from builder.patrol import run_patrol
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedCanAffordHarvesterError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "can afford a harvester, should build instead of patrol"


class TaskRejectedPatrolFailedError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "run_patrol produced no action"


def patrol_cheap(self: Builder, ct: Controller) -> None:
    if can_afford(self, EntityType.HARVESTER):
        raise TaskRejectedCanAffordHarvesterError
    if not run_patrol(self, ct):
        raise TaskRejectedPatrolFailedError
