"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/ore/claim_ore.py`.

Walk onto an unharvested ore tile to claim it. Highest-priority of
the three ore-claim phases. Single responsibility: navigate (with
contest-clearing) onto `ore_target` or `ax_ore_target`. No conveyor
placement, no harvester placement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.harvest import walk_to_ore_claim
from builder.helpers import ore_available
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult


def resolve_target(self_):
    t = self_.ore_target
    if t is not None:
        return t
    t = self_.ax_ore_target
    if t is not None and (self_.ax_sink is not None):
        return t
    return None


def claim_ore(self_, ct):
    target = resolve_target(self_)
    if target is None:
        return TaskRejected("no ore_target / ax_ore_target to claim")
    if self_.my_pos == target:
        return TaskRejected.from_string(f"already standing on ore {target!r}")
    if not ore_available(self_, target):
        return TaskRejected.from_string(f"ore {target!r} no longer available")
    if not walk_to_ore_claim(self_, ct, target):
        return TaskRejected.from_string(f"could not progress toward ore {target!r}")
    return None
