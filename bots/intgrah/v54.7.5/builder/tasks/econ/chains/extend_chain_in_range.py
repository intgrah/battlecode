"""Lay a conveyor segment from `dangling_output` toward its sink, only
when the dangling end is within builder vision (d² <= 20). Higher-priority
than the approach variant — restricts chain extension to ends the
builder can actually see, so distant dangling ends discovered earlier
don't outrank harvesting work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from util.metrics import claims_by_proximity

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


class TaskRejectedNotClosestError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "another builder is closer to dangling {target}", {"target": self.target}


def extend_chain_in_range(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
    if not ct.is_in_vision(self.dangling_output):
        raise TaskRejectedOutOfVisionError(self.dangling_output)
    if not claims_by_proximity(
        self.my_pos,
        self.my_id,
        self.dangling_output,
        (
            (fb_pos, fb_id)
            for fb_pos, fb_id in self.all_bots.items()
            if fb_id != self.my_id and fb_pos in self.friendly_bots
        ),
    ):
        raise TaskRejectedNotClosestError(self.dangling_output)
    extend_chain(self, ct, self.dangling_output)
