"""Place a barrier on an unbuilt walkable tile cardinal to one of our
harvesters, walling off the harvester from parasitic gunner placements.
Barriers (30 HP, 3 Ti) take far more chip damage to clear than a road.

I/O exclusion: a cardinal that's a flow path / shared with another
harvester / chosen as the harvester's feed direction must NOT be
barriered, or the harvester gets sealed off and never produces. The
exclusion list is computed per-adjacent-harvester via
`harvester_io_cardinals`; we skip any tile reserved by ANY adjacent
harvester.

One barrier per turn; rejects if no eligible tile is reachable and
buildable right now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingHarvester, BuildingMarker, BuildingRoad
from cambc import EntityType, Environment
from util.directions import DIR4

from builder.helpers import harvester_io_cardinals, try_place
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoUnbuiltHarvesterNeighbourError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no unbuilt walkable tile adjacent to a friendly harvester"


def _adjacent_ti_harvester_ores(self: Builder, pos: Position) -> list[Position]:
    """Ore tiles whose cardinal includes `pos` AND host a friendly
    Ti harvester. Ax harvesters are excluded — Ax can't be parasitised
    so there's nothing to wall off, and barriers there would just cost
    Ti without defensive value.
    """
    out: list[Position] = []
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if not (isinstance(b, BuildingHarvester) and b.team == self.my_team):
            continue
        if self.get_env(n) != Environment.ORE_TITANIUM:
            continue
        out.append(n)
    return out


def pave_near_harvester(self: Builder, ct: Controller) -> None:
    for pos in self.nearby_tiles:
        if pos not in self.adjacent_to_harvester:
            continue
        if self.get_env(pos) == Environment.WALL:
            continue
        # Cheaply destroyable buildings (friendly road, any marker) are
        # treated as "empty" — try_place will demolish them. Anything
        # else (conveyor, harvester, foundry, enemy building) blocks.
        b = self.get_building(pos)
        if b is not None and not isinstance(b, BuildingRoad | BuildingMarker):
            continue
        # Restrict to tiles cardinal to a Ti harvester. Ax harvesters
        # don't get barriered.
        ore_tiles = _adjacent_ti_harvester_ores(self, pos)
        if not ore_tiles:
            continue
        # I/O exclusion: skip tiles that any adjacent harvester reserves
        # as its flow / feed slot.
        if any(pos in harvester_io_cardinals(self, ore) for ore in ore_tiles):
            continue
        if try_place(self, ct, EntityType.BARRIER, pos):
            return
    raise TaskRejectedNoUnbuiltHarvesterNeighbourError
