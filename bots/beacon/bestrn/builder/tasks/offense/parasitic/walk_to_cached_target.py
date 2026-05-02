"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/parasitic/walk_to_cached_target.py`.

Walk back toward a cached `offense_target` when no fresh harvester is
visible. Used when a builder commits to a target, walks out of vision of
it, then needs to keep walking back. Routes via `offense_launcher` if
one is set and the target is far; else direct.
"""
from __future__ import annotations

from cambc import EntityType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move
from builder.tasks.offense.helpers import vulnerable_harvesters
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult

def walk_to_cached_target(self_, ct):
    if not (not vulnerable_harvesters(self_)):
        return TaskRejected("a vulnerable harvester is in vision — approach it first")
    offense_target = self_.offense_target
    if offense_target is None:
        return TaskRejected("offense_target is None")
    ol = self_.offense_launcher
    if ol is not None and (self_.building_kind[self_.idx(ol)] == EntityType.LAUNCHER) and (self_.building_team[self_.idx(ol)] == self_.my_team) and (self_.my_pos.distance_squared(offense_target) > 8):
        make_move(self_, ct, ol)
        return None
    make_move(self_, ct, offense_target)
    return None
