"""Lay a conveyor segment from `dangling_output` toward its sink, only
when the dangling end is within builder vision. The cached
`dangling_output` is refreshed every turn by `update_dangling` (no
stickiness), and the proximity gate inside the picker ensures only the
rightful claimant builder considers a given end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import extend_chain
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoDanglingOutputError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no dangling output"


class TaskRejectedOutOfVisionError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "dangling {target} not in vision", {"target": self.target}


def extend_chain_in_range(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    if not ct.is_in_vision(self.dangling_output):
        raise TaskRejectedOutOfVisionError(self.dangling_output)
    extend_chain(self, ct, self.dangling_output)
