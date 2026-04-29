"""Step off the claimed offensive ore and place a Ti harvester. Mirrors
`build_harvester` (and shares its anchor-when-waiting semantics)."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType
from util.debug import debug as log

from builder.harvest import clear_barriered_feed, step_off_and_build_harvester
from builder.helpers import (
    can_afford,
    harvester_feed_cardinal,
    ore_available,
)
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoOffensiveOreError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "offensive_ore_target is None"


class TaskRejectedNotOnOreError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "not on offensive ore {target}", {"target": self.target}


def build_offensive_harvester(self: Builder, ct: Controller) -> None:
    target = self.offensive_ore_target
    if target is None:
        raise TaskRejectedNoOffensiveOreError
    if self.my_pos != target:
        raise TaskRejectedNotOnOreError(target)
    if not ore_available(self, target):
        raise TaskRejectedNoOffensiveOreError
    # Anchor on the ore — wait for Ti / feed availability rather than
    # rejecting and letting `explore` wander us off.
    if not can_afford(self, EntityType.HARVESTER):
        log("build_offensive_harvester: waiting on Ti for {target}", target=target)
        return
    if harvester_feed_cardinal(self, target) is None:
        # Last-resort: clear a friendly barrier on a cardinal closest
        # to sink so next turn the feed picker has somewhere to land.
        if not clear_barriered_feed(self, ct, target):
            log(
                "build_offensive_harvester: no feed cardinal for {target}; waiting",
                target=target,
            )
        return
    if not step_off_and_build_harvester(self, ct, target):
        log(
            "build_offensive_harvester: cannot step off {target}; waiting",
            target=target,
        )
