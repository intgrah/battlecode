"""Guard work around our Ti harvesters / claimed-but-unbuilt ore tiles.
Two kinds of action, both fired one-per-turn from this task:

1. Guard on a non-I/O cardinal that's currently unguarded. The choice
   between BARRIER and inward-facing CONVEYOR is `place_harvester_guard`'s
   call — barrier when the cardinal already has >=3 walkable neighbours
   (builders can route around; barriers are fire-immune), conveyor
   otherwise (walkable, preserves connectivity in tight geometry).
   Inward conveyors point back at the harvester so dangling-end
   classification ignores them.

2. Road on the feed (output) cardinal if it isn't already walkable.
   The builder will eventually step off the ore onto this tile to
   place the harvester; the engine requires a walkable building
   (road minimum) on the destination, so paving the feed ahead of
   time means the step-off happens immediately when Ti is available.

Already-guarded cardinals — walls, harvesters (any team), or any
non-walkable building — count as guards: no guard is needed there.
So a harvester adjacent to two harvesters plus a wall has nothing
to pave on those three sides.

I/O exclusion: the cardinal chosen as the harvester's feed slot, or
that already hosts a flow consumer, is reserved against guard
placement (but the feed gets the road-prep treatment instead).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingHarvester
from cambc import EntityType, Environment
from util.debug import debug as log
from util.directions import DIR4

from builder.harvest import (
    needs_harvester_guard,
    place_harvester_guard,
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


class TaskRejectedNoGuardCandidateError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "nothing to guard around any visible harvester / claim"


def guard_harvester_neighbours(self: Builder, ct: Controller) -> None:
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
    # Only ECON / DEFENSE claims — offensive_ore_target is excluded
    # because OFFENSE has its own task tree (no guard pass) and a
    # role-mismatched builder standing on an offensive claim won't ever
    # have build_harvester fire (its `_resolve_target` ignores
    # `offensive_ore_target`). Including it here would just leave dead
    # barrier rings on the enemy side after the builder wanders off.
    for tgt in (self.ore_target, self.ax_ore_target):
        if tgt is not None and self.my_pos == tgt and tgt not in targets:
            targets.append(tgt)

    if not targets:
        raise TaskRejectedNoGuardCandidateError

    near = set(self.nearby_tiles)
    affords_road = can_afford(self, EntityType.ROAD)
    # Both barrier and conveyor cost the same in Ti, so a single check
    # suffices for the guard placement branch.
    affords_guard = can_afford(self, EntityType.CONVEYOR)

    # Aggregate I/O reservations across ALL adjacent targets — a
    # cardinal that's the feed (or already a flow consumer) of any
    # target must not be guarded by another target's ring. Fixes the
    # livelock where harvester X's feed kept getting barriered by
    # harvester Y's guard pass and re-destroyed by X's feed-prep.
    no_guard: set[Position] = set()
    for target in targets:
        no_guard |= harvester_io_cardinals(self, target)

    for target in targets:
        feed = harvester_feed_cardinal(self, target)
        if feed is None:
            continue

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
                "guard_harvester_neighbours: ROAD on feed {feed} (prep step-off)",
                feed=feed,
            )
            ct.build_road(feed)
            return

        if not affords_guard:
            continue
        for d in DIR4:
            pos = target.add(d)
            if pos not in near:
                continue
            if pos in no_guard:
                continue
            if not needs_harvester_guard(self, pos, target, no_guard):
                continue
            if place_harvester_guard(self, ct, pos, target):
                return
    raise TaskRejectedNoGuardCandidateError
