"""Destroy any nearby tile that `leads_to_enemy_building` (i.e. a
friendly conveyor whose downstream chain ultimately reaches an enemy
building, leaking our resources to them) and pave a road in its place.
First tile in vision that qualifies wins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoEnemyConveyorInRangeError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no enemy-feeding conveyor in action range"


def fix_enemy_conveyor(self: Builder, ct: Controller) -> None:
    for pos in self.nearby_tiles:
        if self.leads_to_enemy_building(pos) and ct.can_destroy(pos):
            ct.destroy(pos)
            self.apply_local_destroy(pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
                return
    raise TaskRejectedNoEnemyConveyorInRangeError
