"""Extend `dangling_output` toward the enemy core (instead of `ti_sink`
or `my_core`). Used after a forward harvester is planted, growing the
offensive chain toward enemy lines. Requires symmetry to be resolved so
`en_core_guess` returns a known position.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import ResourceType

from builder.chain_routing import extend_step, resource_at
from builder.helpers import on_enemy_side
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedSymmetryUnresolvedError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "symmetry unresolved; en_core unknown"


class TaskRejectedNoDanglingOutputError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no dangling output"


class TaskRejectedDanglingNotOffensiveError(TaskRejectedError):
    def __init__(self, start: Position) -> None:
        self.start = start

    @override
    def reason(self) -> Reason:
        return "dangling {start} is on our side of the bisector", {"start": self.start}


class TaskRejectedDanglingNotTiError(TaskRejectedError):
    def __init__(self, start: Position, resource: ResourceType | None) -> None:
        self.start = start
        self.resource = resource

    @override
    def reason(self) -> Reason:
        return "dangling {start} is {resource}, push_extend is Ti-only", {
            "start": self.start,
            "resource": self.resource,
        }


def push_extend(self: Builder, ct: Controller) -> None:
    if self.symmetry is None:
        raise TaskRejectedSymmetryUnresolvedError
    start = self.dangling_output
    if start is None:
        raise TaskRejectedNoDanglingOutputError
    if not on_enemy_side(self, start):
        raise TaskRejectedDanglingNotOffensiveError(start)
    resource = resource_at(self, start)
    if resource != ResourceType.TITANIUM:
        raise TaskRejectedDanglingNotTiError(start, resource)
    target = self.en_core_guess
    # Raises a chain_routing TaskRejectedError on no-op.
    extend_step(self, ct, start, target, ResourceType.TITANIUM)
