from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import route_chain
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoDanglingOutputError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no dangling output"


class TaskRejectedRouteFailedError(TaskRejectedError):
    def __init__(self, start: Position) -> None:
        self.start = start

    @override
    def __str__(self) -> str:
        return f"route_chain from {self.start} produced no action"


def extend_chain_approach(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    if not route_chain(self, ct, self.dangling_output):
        raise TaskRejectedRouteFailedError(self.dangling_output)
