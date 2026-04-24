from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.heal import heal_builders, run_heal
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNothingToHeal(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no damaged buildings or builders to heal"


def heal(self: Builder, ct: Controller) -> None:
    if not (run_heal(self, ct) or heal_builders(self, ct)):
        raise TaskRejectedNothingToHeal
