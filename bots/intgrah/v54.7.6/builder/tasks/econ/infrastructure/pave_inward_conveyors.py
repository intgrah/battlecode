"""Prep work around our Ti harvesters / claimed-but-unbuilt ore tiles.
Two kinds of action, both fired one-per-turn from this task:

1. Inward-facing conveyor on a non-I/O cardinal that's currently
   unguarded (empty / friendly road / marker). The conveyor points
   back at the target so it acts as a guard (denies the tile to enemy
   parasitic placements) without confusing flow routing — dangling-end
   classification ignores conveyors pointing INTO a harvester.

2. Road on the feed (output) cardinal if it's empty terrain. The
   builder will eventually step off the ore onto this tile to place
   the harvester; the engine requires a walkable building (road
   minimum) on the destination, so paving the feed ahead of time
   means the step-off happens immediately when Ti is available.

Already-guarded cardinals — walls, harvesters (any team), or any
non-walkable building — count as guards: no inward conveyor is needed
there. So a harvester adjacent to two harvesters plus a wall has
nothing to pave on those three sides.

I/O exclusion: the cardinal chosen as the harvester's feed slot, or
that already hosts a flow consumer, is reserved against inward-conveyor
placement (but the feed gets the road-prep treatment instead).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingHarvester
from cambc import Environment, EntityType
from util.debug import debug as log
from util.directions import DIR4

from builder.harvest import (
    needs_inward_guard,
    place_inward_conveyor,
)
from builder.helpers import (
    can_afford,
    harvester_feed_cardinal,
    harvester_io_cardinals,
)
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoPaveCandidateError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "nothing to pave around any visible harvester / claim"


def pave_inward_conveyors(self: Builder, ct: Controller) -> None:
    # Iterate the (small) set of harvester / claim targets in range,
    # rather than all nearby tiles. Each target has at most 4 cardinals;
    # the inner work (feed cardinal, I/O reservation, guard checks)
    # runs once per target instead of once per nearby tile.
    targets: list[Position] = []
    for pos in self.nearby_tiles:
        b = self.get_building(pos)
        if (
            isinstance(b, BuildingHarvester)
            and b.team == self.my_team
            and self.get_env(pos) == Environment.ORE_TITANIUM
        ):
            targets.append(pos)
    for tgt in (self.ore_target, self.ax_ore_target, self.offensive_ore_target):
        if tgt is not None and self.my_pos == tgt and tgt not in targets:
            targets.append(tgt)

    if not targets:
        raise TaskRejectedNoPaveCandidateError

    near = set(self.nearby_tiles)
    affords_road = can_afford(self, EntityType.ROAD)
    affords_conveyor = can_afford(self, EntityType.CONVEYOR)

    for target in targets:
        feed = harvester_feed_cardinal(self, target)
        if feed is None:
            continue
        io_reserved = harvester_io_cardinals(self, target)

        # Feed-prep: pave a road on the feed cardinal if it isn't
        # already walkable. Markers (1 HP, overbuildable) and empty
        # terrain both have cost > 1 in the grid; friendly roads /
        # conveyors etc. are cost 1 and need no prep.
        if (
            affords_road
            and feed in near
            and self.get_cost(feed) > 1
            and ct.can_build_road(feed)
        ):
            log(
                "pave_inward_conveyors: ROAD on feed {feed} (prep step-off)",
                feed=feed,
            )
            ct.build_road(feed)
            return

        # Inward-guard placement on a non-I/O cardinal that needs guarding.
        if not affords_conveyor:
            continue
        for d in DIR4:
            pos = target.add(d)
            if pos not in near:
                continue
            if pos in io_reserved:
                continue
            if not needs_inward_guard(self, pos, target, io_reserved):
                continue
            if place_inward_conveyor(self, ct, pos, target):
                return
    raise TaskRejectedNoPaveCandidateError
