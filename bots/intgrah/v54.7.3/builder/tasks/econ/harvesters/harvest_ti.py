"""Walk to `ore_target` and place a Ti harvester. Delegates to
`build_at_ore` for the ore-claim approach + harvester-build sequence
(contest-clearing, neighbour paving, step-off-and-build).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import build_at_ore
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoTiOreTargetError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "ore_target is None"


class TaskRejectedHarvestFailedError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "build_at_ore({target}) produced no action", {"target": self.target}


def harvest_ti(self: Builder, ct: Controller) -> None:
    if self.ore_target is None:
        raise TaskRejectedNoTiOreTargetError
    if not build_at_ore(self, ct, self.ore_target):
        raise TaskRejectedHarvestFailedError(self.ore_target)
