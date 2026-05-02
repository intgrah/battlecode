"""Walk onto an unharvested ore tile to claim it. Highest-priority of
the three ore-claim phases. Single responsibility: navigate (with
contest-clearing) onto `ore_target` or `ax_ore_target`. No conveyor
placement, no harvester placement.

Rejects when:
  - no ore claim target is set,
  - the chosen target's ore is no longer available
    (`ore_available` returns False),
  - we already stand on the target (claim done; defer to pave/build).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.harvest import walk_to_ore_claim
from builder.helpers import ore_available
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoOreClaimError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no ore_target / ax_ore_target to claim"


class TaskRejectedAlreadyOnOreError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "already standing on ore {target}", {"target": self.target}


class TaskRejectedOreUnavailableError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "ore {target} no longer available", {"target": self.target}


class TaskRejectedClaimNoProgressError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "could not progress toward ore {target}", {"target": self.target}


def _resolve_target(self: Builder) -> Position | None:
    if self.ore_target is not None:
        return self.ore_target
    if self.ax_ore_target is not None and self.ax_sink is not None:
        return self.ax_ore_target
    return None


def claim_ore(self: Builder, ct: Controller) -> None:
    target = _resolve_target(self)
    if target is None:
        raise TaskRejectedNoOreClaimError
    if self.my_pos == target:
        raise TaskRejectedAlreadyOnOreError(target)
    if not ore_available(self, target):
        raise TaskRejectedOreUnavailableError(target)
    if not walk_to_ore_claim(self, ct, target):
        raise TaskRejectedClaimNoProgressError(target)
