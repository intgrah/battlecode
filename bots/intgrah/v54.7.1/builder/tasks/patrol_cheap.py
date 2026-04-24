from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType

from builder.helpers import can_afford
from builder.patrol import run_patrol
from builder.role import Role
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNotDefensive(TaskRejectedError):
    def __init__(self, role: Role | None) -> None:
        self.role = role

    @override
    def __str__(self) -> str:
        return f"role={self.role}, requires DEFENSE"


class TaskRejectedCanAffordHarvester(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "can afford a harvester, should build instead of patrol"


class TaskRejectedPatrolFailed(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "run_patrol produced no action"


def patrol_cheap(self: Builder, ct: Controller) -> None:
    if self.role != Role.DEFENSE:
        raise TaskRejectedNotDefensive(self.role)
    if can_afford(self, EntityType.HARVESTER):
        raise TaskRejectedCanAffordHarvester
    if not run_patrol(self, ct):
        raise TaskRejectedPatrolFailed
