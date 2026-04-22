from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingMarker,
    BuildingRoad,
)
from cambc import EntityType, Environment
from util.constants import MAX_WIDTH

from builder.helpers import try_place
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoCongestedConveyorError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no congested conveyor upgradeable to a splitter in range"


def _is_free_tile(self: Builder, pos: Position) -> bool:
    """Cheap to overwrite: empty terrain with no building, friendly road,
    or any marker. Walls and other buildings are excluded."""
    if not self.in_bounds(pos):
        return False
    i = pos.y * MAX_WIDTH + pos.x
    if self.env[i] == Environment.WALL:
        return False
    b = self.buildings[i]
    if b is None:
        return self.env[i] == Environment.EMPTY
    if isinstance(b, BuildingRoad) and b.team == self.my_team:
        return True
    return isinstance(b, BuildingMarker)


def resolve_congestion(self: Builder, ct: Controller) -> None:
    """Upgrade a friendly conveyor on a feeder chain of a congested
    junction into a splitter. Congestion is rooted at an overcapacity
    junction (feeders' total inflow exceeds the junction's single-tile
    pass-through); replacing a conveyor upstream of it with a splitter
    forks flow away from the bottleneck."""
    if not self.upstream_of_congestion:
        raise TaskRejectedNoCongestedConveyorError
    for pos in self.nearby_buildings:
        if pos not in self.upstream_of_congestion:
            continue
        i = pos.y * MAX_WIDTH + pos.x
        bld = self.buildings[i]
        if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
            continue
        if bld.team != self.my_team:
            continue
        feeders = self.in_edges[i]
        if len(feeders) != 1:
            continue
        if pos in self.upstream_of_dangling:
            continue
        feeder = feeders[0]
        d_new = feeder.direction_to(pos)
        original_out = pos.add(bld.direction)
        new_outs = [
            pos.add(d_new.rotate_right().rotate_right()),
            pos.add(d_new.rotate_left().rotate_left()),
        ]
        new_outs = [o for o in new_outs if o != original_out]
        if not any(_is_free_tile(self, o) for o in new_outs):
            continue
        if try_place(self, ct, EntityType.SPLITTER, pos, d_new):
            return
    raise TaskRejectedNoCongestedConveyorError
