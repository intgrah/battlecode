"""Walk to `ax_ore_target` and place an Ax harvester. Gated on `ax_sink`
being set — without a sink, raw Ax is destroyed when delivered to the
core or to turrets, so we won't bother. Delegates to `build_at_ore` for
the ore-claim approach + harvester-build sequence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import build_at_ore
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoAxSinkError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "ax_sink is None"


class TaskRejectedNoAxOreTargetError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "ax_ore_target is None"


class TaskRejectedHarvestFailedError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "build_at_ore({target}) produced no action", {"target": self.target}


def harvest_ax(self: Builder, ct: Controller) -> None:
    if self.ax_sink is None:
        raise TaskRejectedNoAxSinkError
    if self.ax_ore_target is None:
        raise TaskRejectedNoAxOreTargetError
    if not build_at_ore(self, ct, self.ax_ore_target):
        raise TaskRejectedHarvestFailedError(self.ax_ore_target)
