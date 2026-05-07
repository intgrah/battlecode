"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/patrol_late.py`.

Late-game defensive patrol: only fires when at least one friendly
harvester is in vision (otherwise there's nothing to defend nearby).
Lower priority than `patrol_cheap` in the DEFENSE policy — the cheap
variant gates on "broke", this one gates on "have something to guard".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from builder.patrol import run_patrol
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult


def patrol_late(self_, ct):
    if not self_.adjacent_to_harvester:
        return TaskRejected("no friendly harvester-adjacent tile in view")
    if not run_patrol(self_, ct):
        return TaskRejected("run_patrol produced no action")
    return None
