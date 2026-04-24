from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import build_at_ore
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoOffensiveOreError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "offensive_ore_target is None"


class TaskRejectedOffensiveHarvestFailedError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def __str__(self) -> str:
        return f"build_at_ore({self.target}) produced no action"


def place_offensive_harvester(self: Builder, ct: Controller) -> None:
    if self.offensive_ore_target is None:
        raise TaskRejectedNoOffensiveOreError
    if not build_at_ore(self, ct, self.offensive_ore_target):
        raise TaskRejectedOffensiveHarvestFailedError(self.offensive_ore_target)
