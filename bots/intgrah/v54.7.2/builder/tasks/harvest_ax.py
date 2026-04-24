from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import build_at_ore
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoAxSinkError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "ax_sink is None"


class TaskRejectedNoAxOreTargetError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "ax_ore_target is None"


class TaskRejectedHarvestFailedError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def __str__(self) -> str:
        return f"build_at_ore({self.target}) produced no action"


def harvest_ax(self: Builder, ct: Controller) -> None:
    if self.ax_sink is None:
        raise TaskRejectedNoAxSinkError
    if self.ax_ore_target is None:
        raise TaskRejectedNoAxOreTargetError
    if not build_at_ore(self, ct, self.ax_ore_target):
        raise TaskRejectedHarvestFailedError(self.ax_ore_target)
