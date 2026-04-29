"""Place an inward-facing conveyor on a tile cardinal to one of our Ti
harvesters, replacing the older barrier-ring strategy. The conveyor
points back toward the harvester so it acts as a guard (denies the tile
to enemy parasitic-gunner placements) without confusing flow routing —
the dangling-end check ignores conveyors that point INTO a harvester
(those aren't flow consumers; they don't form a stray dangling end).

I/O exclusion: a cardinal that's a real flow path / shared with another
harvester / chosen as the harvester's feed direction must NOT be paved
inward — it'd block the harvester's actual output.

One conveyor per turn; rejects if no eligible tile is buildable now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingHarvester, BuildingMarker, BuildingRoad
from cambc import EntityType, Environment
from util.directions import DIR4

from builder.helpers import can_afford, harvester_io_cardinals
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoUnbuiltHarvesterNeighbourError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no unbuilt walkable tile adjacent to a friendly harvester"


def _adjacent_ti_harvester_ores(self: Builder, pos: Position) -> list[Position]:
    """Ore tiles whose cardinal includes `pos` AND host a friendly Ti
    harvester. Ax harvesters are excluded — Ax can't be parasitised so
    there's nothing to guard."""
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
        # treated as "empty" — we'll demolish before building. Anything
        # else (conveyor, harvester, foundry, enemy building) blocks.
        b = self.get_building(pos)
        if b is not None and not isinstance(b, BuildingRoad | BuildingMarker):
            continue
        # Restrict to tiles cardinal to a Ti harvester.
        ore_tiles = _adjacent_ti_harvester_ores(self, pos)
        if not ore_tiles:
            continue
        # I/O exclusion: skip tiles that any adjacent harvester reserves
        # as its flow / feed slot.
        if any(pos in harvester_io_cardinals(self, ore) for ore in ore_tiles):
            continue
        # Pick the first adjacent harvester as the inward target. The
        # conveyor will face from `pos` toward that harvester.
        target = ore_tiles[0]
        if not can_afford(self, EntityType.CONVEYOR):
            return
        inward = pos.direction_to(target)
        if isinstance(self.get_building(pos), BuildingRoad) and ct.can_destroy(pos):
            ct.destroy(pos)
        if ct.can_build_conveyor(pos, inward):
            ct.build_conveyor(pos, inward)
            return
    raise TaskRejectedNoUnbuiltHarvesterNeighbourError
