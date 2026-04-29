"""Walk toward `dangling_output` and lay a conveyor segment along the
A* path to its sink (Ti -> ti_sink, Ax -> ax_sink). No range gate — the
builder will travel as far as needed. Used when the dangling end is too
far for the in-range variant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.chain_routing import extend_chain
from builder.tasks.rejected import Reason, TaskRejectedError
from util.metrics import claims_by_proximity

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoDanglingOutputError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no dangling output"


class TaskRejectedNotClosestError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "another builder is closer to dangling {target}", {"target": self.target}


def extend_chain_approach(self: Builder, ct: Controller) -> None:
    if self.dangling_output is None:
        raise TaskRejectedNoDanglingOutputError
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
