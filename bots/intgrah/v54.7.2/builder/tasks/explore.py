"""Walk toward unexplored tiles to grow the bot's known map. Gated on
`ti > EXPLORE_MIN_TI`: exploring lays roads, so a starving bot would
strand titanium it can't recoup. Delegates the actual movement to
`builder.explore`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, override

from builder.explore import explore as run_explore
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

EXPLORE_MIN_TI: Final = 100


class TaskRejectedInsufficientTiError(TaskRejectedError):
    def __init__(self, have: int) -> None:
        self.have = have

    @override
    def __str__(self) -> str:
        return f"ti={self.have} <= {EXPLORE_MIN_TI}; exploring would burn roads we can't recoup"


def explore(self: Builder, ct: Controller) -> None:
    if self.ti <= EXPLORE_MIN_TI:
        raise TaskRejectedInsufficientTiError(self.ti)
    run_explore(self, ct)
