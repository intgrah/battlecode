from __future__ import annotations

from typing import TYPE_CHECKING, override

from util.directions import DIR8

from builder.helpers import try_move_dir, try_move_with_road
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoMoveAvailable(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no direction produced a legal move or road-placement"


def wander(self: Builder, ct: Controller) -> None:
    dir8 = DIR8.copy()
    self.rng.shuffle(dir8)
    if not (
        any(try_move_dir(ct, d) for d in dir8)
        or any(try_move_with_road(self, ct, self.my_pos.add(d)) for d in dir8)
    ):
        raise TaskRejectedNoMoveAvailable
