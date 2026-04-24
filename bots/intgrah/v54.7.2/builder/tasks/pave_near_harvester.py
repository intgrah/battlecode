from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Environment

from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoUnbuiltHarvesterNeighbourError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no unbuilt walkable tile adjacent to a friendly harvester"


def pave_near_harvester(self: Builder, ct: Controller) -> None:
    for pos in self.nearby_tiles:
        if (
            pos in self.adjacent_to_harvester
            and not self.get_building(pos)
            and self.get_env(pos) != Environment.WALL
            and ct.can_build_road(pos)
        ):
            ct.build_road(pos)
            return
    raise TaskRejectedNoUnbuiltHarvesterNeighbourError
