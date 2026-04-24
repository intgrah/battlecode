from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import route_chain
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoDanglingOutput(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no dangling output"


class TaskRejectedOutOfRange(TaskRejectedError):
    def __init__(self, target: Position, dist_sq: int) -> None:
        self.target = target
        self.dist_sq = dist_sq

    @override
    def __str__(self) -> str:
        return f"dangling {self.target} at dist²={self.dist_sq} > 2"


class TaskRejectedRouteFailed(TaskRejectedError):
    def __init__(self, start: Position) -> None:
        self.start = start

    @override
    def __str__(self) -> str:
        return f"route_chain from {self.start} produced no action"


def extend_chain_in_range(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutput
    dist_sq = self.my_pos.distance_squared(self.dangling_output)
    if dist_sq > 2:
        raise TaskRejectedOutOfRange(self.dangling_output, dist_sq)
    if not route_chain(self, ct, self.dangling_output):
        raise TaskRejectedRouteFailed(self.dangling_output)
