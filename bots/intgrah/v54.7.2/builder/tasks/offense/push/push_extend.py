"""Extend `dangling_output` toward the enemy core (instead of `ti_sink`
or `my_core`). Used after a forward harvester is planted, growing the
offensive chain toward enemy lines. Requires symmetry to be resolved so
`get_enemy_core_pos` returns a known position.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import route_chain_toward
from builder.helpers import get_enemy_core_pos
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


class TaskRejectedRouteFailedError(TaskRejectedError):
    def __init__(self, start: Position) -> None:
        self.start = start

    @override
    def reason(self) -> Reason:
        return "route_chain_toward from {start} produced no action", {
            "start": self.start
        }


def push_extend(self: Builder, ct: Controller) -> None:
    if self.symmetry is None:
        raise TaskRejectedSymmetryUnresolvedError
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    target = get_enemy_core_pos(self)
    if not route_chain_toward(self, ct, self.dangling_output, target):
        raise TaskRejectedRouteFailedError(self.dangling_output)
