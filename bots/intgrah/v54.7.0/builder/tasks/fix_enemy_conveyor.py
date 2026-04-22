from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoEnemyConveyorInRange(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no enemy-feeding conveyor in action range"


def fix_enemy_conveyor(self: Builder, ct: Controller) -> None:
    for pos in self.nearby_tiles:
        if self.leads_to_enemy_building(pos) and ct.can_destroy(pos):
            ct.destroy(pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return
    raise TaskRejectedNoEnemyConveyorInRange
