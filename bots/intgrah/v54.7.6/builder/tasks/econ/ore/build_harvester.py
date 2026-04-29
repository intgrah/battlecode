"""Step off the claimed ore tile and place a harvester in the same
turn. Lowest-priority of the three ore-claim phases — fires only after
`claim_ore` is satisfied (we stand on the ore) and `pave_inward_conveyors`
has nothing more to add to the ring.

When standing on the ore but unable to build (waiting on Ti, no viable
feed cardinal yet, no escape direction), this task silently succeeds
without action — the builder anchors to the ore and waits, instead of
falling through to `explore` and wandering off.

Rejects (so siblings can fire) only when the builder is not on the ore
or no claim target exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import EntityType
from util.debug import debug as log

from builder.harvest import step_off_and_build_harvester
from builder.helpers import (
    can_afford,
    harvester_feed_cardinal,
    ore_available,
)
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoOreClaimError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no ore_target / ax_ore_target to harvest"


class TaskRejectedNotOnOreError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "not standing on ore {target}", {"target": self.target}


def _resolve_target(self: Builder) -> Position | None:
    if self.ore_target is not None:
        return self.ore_target
    if self.ax_ore_target is not None and self.ax_sink is not None:
        return self.ax_ore_target
    return None


def build_harvester(self: Builder, ct: Controller) -> None:
    target = _resolve_target(self)
    if target is None:
        raise TaskRejectedNoOreClaimError
    if self.my_pos != target:
        raise TaskRejectedNotOnOreError(target)
    if not ore_available(self, target):
        self.ore_target = None
        raise TaskRejectedNoOreClaimError
    # From here on the builder is anchored to the ore. Any inability to
    # complete the build is a "wait" not a "reject" — we don't want
    # `explore` to wander us off a claimed tile.
    if not can_afford(self, EntityType.HARVESTER):
        log(f"build_harvester: waiting on Ti to build HARVESTER on {target}")
        return
    if harvester_feed_cardinal(self, target) is None:
        log(f"build_harvester: no viable feed cardinal for {target}; waiting")
        return
    if not step_off_and_build_harvester(self, ct, target):
        log(f"build_harvester: could not step off {target} this turn; waiting")
