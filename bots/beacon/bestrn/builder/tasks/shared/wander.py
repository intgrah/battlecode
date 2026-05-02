"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/wander.py`.

Walk-away-from-core fallback for ECON / DEFENSE roles. Tries each
of the 8 directions in order of decreasing Chebyshev distance from
our core, walking only on pre-existing walkable tiles — no road
paving (no Ti spend). Rejects if no direction produces a legal move.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import try_move_dir
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.directions import DIR8
from util.metrics import chebyshev

def wander(self_, ct):
    my_pos = self_.my_pos
    my_core = self_.my_core
    dirs = list(DIR8)
    dirs.sort(key=lambda d: -chebyshev(my_pos.add(d), my_core))
    for d in dirs:
        if try_move_dir(ct, d):
            return None
    return TaskRejected("no walkable direction available without paving")
