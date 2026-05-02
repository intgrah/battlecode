"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/patrol_cheap.py`.

Walk a defensive route around our economy, but only when we can't
afford a harvester (otherwise the Ti is better spent on another harvester
build). Used by DEFENSE role early-game when funds are tight; later the
late-patrol variant takes over.
"""
from __future__ import annotations

from cambc import EntityType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import can_afford
from builder.patrol import run_patrol
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult

def patrol_cheap(self_, ct):
    if can_afford(self_, EntityType.HARVESTER):
        return TaskRejected("can afford a harvester, should build instead of patrol")
    if not run_patrol(self_, ct):
        return TaskRejected("run_patrol produced no action")
    return None
