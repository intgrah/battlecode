"""Plant a Ti harvester on enemy-side ore (`offensive_ore_target`,
selected by the inverse-bisector gate: more than r²=20 closer to enemy
core than to ours). The harvester's output becomes a forward dangling
end that subsequent push tasks route toward the enemy core. Ti only —
offensive Ax is much harder and not in scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import build_at_ore
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoOffensiveOreError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "offensive_ore_target is None"


class TaskRejectedOffensiveHarvestFailedError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "build_at_ore({target}) produced no action", {"target": self.target}


def place_offensive_harvester(self: Builder, ct: Controller) -> None:
    if self.offensive_ore_target is None:
        raise TaskRejectedNoOffensiveOreError
    if not build_at_ore(self, ct, self.offensive_ore_target):
        raise TaskRejectedOffensiveHarvestFailedError(self.offensive_ore_target)
