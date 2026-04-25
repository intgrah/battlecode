"""Lay a conveyor segment from `dangling_output` toward its sink, only
when the builder is already within action range (d² <= 2). Higher-priority
than the approach variant — fires the placement immediately rather than
walking first.
"""

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


class TaskRejectedOutOfRangeError(TaskRejectedError):
    def __init__(self, target: Position, dist_sq: int) -> None:
        self.target = target
        self.dist_sq = dist_sq

    @override
    def __str__(self) -> str:
        return f"dangling {self.target} at dist²={self.dist_sq} > 2"


class TaskRejectedRouteFailedError(TaskRejectedError):
    def __init__(self, start: Position) -> None:
        self.start = start

    @override
    def __str__(self) -> str:
        return f"route_chain from {self.start} produced no action"


def extend_chain_in_range(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    dist_sq = self.my_pos.distance_squared(self.dangling_output)
    if dist_sq > 2:
        raise TaskRejectedOutOfRangeError(self.dangling_output, dist_sq)
    if not route_chain(self, ct, self.dangling_output):
        raise TaskRejectedRouteFailedError(self.dangling_output)
