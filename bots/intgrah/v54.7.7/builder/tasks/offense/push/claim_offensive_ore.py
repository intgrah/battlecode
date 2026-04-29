"""Walk onto `offensive_ore_target` (enemy-side ore picked by the
inverse-bisector gate) to claim it. Mirrors `claim_ore` but uses the
offense-specific target."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import walk_to_ore_claim
from builder.helpers import ore_available
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoOffensiveOreError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "offensive_ore_target is None"


class TaskRejectedAlreadyOnOreError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "already on offensive ore {target}", {"target": self.target}


class TaskRejectedOffensiveOreUnavailableError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "offensive ore {target} unavailable", {"target": self.target}


class TaskRejectedClaimNoProgressError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "no progress toward {target}", {"target": self.target}


def claim_offensive_ore(self: Builder, ct: Controller) -> None:
    target = self.offensive_ore_target
    if target is None:
        raise TaskRejectedNoOffensiveOreError
    if self.my_pos == target:
        raise TaskRejectedAlreadyOnOreError(target)
    if not ore_available(self, target):
        raise TaskRejectedOffensiveOreUnavailableError(target)
    if not walk_to_ore_claim(self, ct, target):
        raise TaskRejectedClaimNoProgressError(target)
