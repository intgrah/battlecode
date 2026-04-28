from __future__ import annotations

from typing import TYPE_CHECKING, override

from cambc import Environment
from util.directions import DIR4
from building import BuildingHarvester, BuildingRoad

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
        if pos not in self.adjacent_to_harvester:
            continue
        if self.get_env(pos) == Environment.WALL:
            continue
        is_road = isinstance(self.get_building(pos), BuildingRoad)
        for d in DIR4:
            adj = pos.add(d)
            if not self.in_bounds(adj):
                continue
            match self.get_building(adj):
                case BuildingHarvester(team=t) if t == self.my_team:
                    if (
                        is_road
                        and ct.can_destroy(pos)
                        and ct.get_conveyor_cost() <= ct.get_global_resources()
                    ):
                        ct.destroy(pos)
                    if ct.can_build_conveyor(pos, d):
                        ct.build_conveyor(pos, d)
                        return
    raise TaskRejectedNoUnbuiltHarvesterNeighbourError
