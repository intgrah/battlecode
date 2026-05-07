"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/ore/build_harvester.py`.

Step off the claimed ore tile and place a harvester in the same
turn. Lowest-priority of the three ore-claim phases — fires only after
`claim_ore` is satisfied (we stand on the ore) and `guard_harvester_neighbours`
has nothing more to add to the ring.
"""

from __future__ import annotations

from cambc import EntityType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.harvest import clear_barriered_feed, step_off_and_build_harvester
from builder.helpers import can_afford, harvester_feed_cardinal, ore_available
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.debug import debug as log
from util.visualiser import auto_wrap_position


def resolve_target(self_):
    t = self_.ore_target
    if t is not None:
        return t
    t = self_.ax_ore_target
    if t is not None and (self_.ax_sink is not None):
        return t
    return None


def build_harvester(self_, ct):
    target = resolve_target(self_)
    if target is None:
        return TaskRejected("no ore_target / ax_ore_target to harvest")
    if self_.my_pos != target:
        return TaskRejected.from_string(f"not standing on ore {target!r}")
    if not ore_available(self_, target):
        self_.ore_target = None
        return TaskRejected("no ore_target / ax_ore_target to harvest")
    if not can_afford(self_, EntityType.HARVESTER):
        args = {}
        args[str("target")] = auto_wrap_position(target)
        log("build_harvester: waiting on Ti for HARVESTER on {target}", args)
        return None
    if harvester_feed_cardinal(self_, target) is None:
        if not clear_barriered_feed(self_, ct, target):
            args = {}
            args[str("target")] = auto_wrap_position(target)
            log("build_harvester: no viable feed cardinal for {target}; waiting", args)
        return None
    if not step_off_and_build_harvester(self_, ct, target):
        args = {}
        args[str("target")] = auto_wrap_position(target)
        log("build_harvester: could not step off {target} this turn; waiting", args)
    return None
