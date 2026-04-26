"""Walk toward `dangling_output` and lay a conveyor segment along the
A* path to its sink (Ti -> ti_sink, Ax -> ax_sink). No range gate — the
builder will travel as far as needed. Used when the dangling end is too
far for the in-range variant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import route_chain
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoDanglingOutputError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no dangling output"


class TaskRejectedRouteFailedError(TaskRejectedError):
    def __init__(self, start: Position) -> None:
        self.start = start

    @override
    def reason(self) -> Reason:
        return "route_chain from {start} produced no action", {"start": self.start}


def extend_chain_approach(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    if not route_chain(self, ct, self.dangling_output):
        raise TaskRejectedRouteFailedError(self.dangling_output)
