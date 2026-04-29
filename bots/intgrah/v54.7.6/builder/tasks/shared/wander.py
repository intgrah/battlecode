"""Walk-away-from-core fallback for ECON / DEFENSE roles. Tries each
of the 8 directions in order of decreasing Chebyshev distance from
our core, walking only on pre-existing walkable tiles — no road
paving (no Ti spend). Rejects if no direction produces a legal move.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from util.directions import DIR8
from util.metrics import chebyshev

from builder.helpers import try_move_dir
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoMoveAvailableError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no walkable direction available without paving"


def wander(self: Builder, ct: Controller) -> None:
    dirs = sorted(DIR8, key=lambda d: -chebyshev(self.my_pos.add(d), self.my_core))
    if not any(try_move_dir(ct, d) for d in dirs):
        raise TaskRejectedNoMoveAvailableError
