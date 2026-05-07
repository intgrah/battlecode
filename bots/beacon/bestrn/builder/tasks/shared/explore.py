"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/explore.py`.

Walk toward unexplored tiles to grow the bot's known map. Gated on
`ti > EXPLORE_MIN_TI`: exploring lays roads, so a starving bot would
strand titanium it can't recoup. Delegates the actual movement to
`builder::explore`.
"""

from __future__ import annotations

from typing import Final

from builder.explore import explore as run_explore
from builder.tasks.rejected import TaskRejected

EXPLORE_MIN_TI: Final[int] = 100


def explore(self_, ct):
    if self_.ti <= 100:
        return TaskRejected.from_string(
            f"ti={self_.ti} <= {100}; exploring would burn roads we can't recoup"
        )
    run_explore(self_, ct)
    return None
