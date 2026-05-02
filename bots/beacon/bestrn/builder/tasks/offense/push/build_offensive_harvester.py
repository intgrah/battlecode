"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/build_offensive_harvester.py`.

Step off the claimed offensive ore and place a Ti harvester. Mirrors
`build_harvester` (and shares its anchor-when-waiting semantics).
"""
from __future__ import annotations

from cambc import EntityType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from builder.harvest import clear_barriered_feed, step_off_and_build_harvester
from builder.helpers import can_afford, harvester_feed_cardinal, ore_available
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.debug import debug as log
from util.visualiser import auto_wrap_position

def build_offensive_harvester(self_, ct):
    target = self_.offensive_ore_target
    if target is None:
        return TaskRejected("offensive_ore_target is None")
    if self_.my_pos != target:
        return TaskRejected.from_string(f"not on offensive ore {target!r}")
    if not ore_available(self_, target):
        return TaskRejected("offensive_ore_target is None")
    if not can_afford(self_, EntityType.HARVESTER):
        args = {}
        args[str("target")] = auto_wrap_position(target)
        log("build_offensive_harvester: waiting on Ti for {target}", args)
        return None
    if (harvester_feed_cardinal(self_, target) is None):
        if not clear_barriered_feed(self_, ct, target):
            args = {}
            args[str("target")] = auto_wrap_position(target)
            log("build_offensive_harvester: no feed cardinal for {target}; waiting", args)
        return None
    if not step_off_and_build_harvester(self_, ct, target):
        args = {}
        args[str("target")] = auto_wrap_position(target)
        log("build_offensive_harvester: cannot step off {target}; waiting", args)
    return None
