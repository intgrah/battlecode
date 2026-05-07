"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/guard_harvester_neighbours.py`.

Guard work around our Ti harvesters / claimed-but-unbuilt ore tiles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Environment

if TYPE_CHECKING:
    from cambc import Position
from util.debug import debug as log
from util.directions import DIR4
from util.visualiser import auto_wrap_position

from builder.harvest import needs_harvester_guard, place_harvester_guard
from builder.helpers import can_afford, harvester_feed_cardinal, harvester_io_cardinals
from builder.tasks.rejected import TaskRejected


def guard_harvester_neighbours(self_, ct):
    targets: list[Position] = []
    for pos in self_.nearby_tiles:
        if (
            self_.building_kind[self_.idx(pos)] == EntityType.HARVESTER
            and self_.building_team[self_.idx(pos)] == self_.my_team
            and self_.env[self_.idx(pos)] == Environment.ORE_TITANIUM
        ):
            targets.append(pos)
    my_pos = self_.my_pos
    for tgt_opt in [self_.ore_target, self_.ax_ore_target]:
        tgt = tgt_opt
        if tgt is not None and (my_pos == tgt) and (tgt not in targets):
            targets.append(tgt)
    if not targets:
        return TaskRejected("nothing to guard around any visible harvester / claim")
    near: set[Position] = list(self_.nearby_tiles)
    affords_road = can_afford(self_, EntityType.ROAD)
    affords_guard = can_afford(self_, EntityType.CONVEYOR)
    no_guard: set[Position] = set()
    for target in targets:
        for p in harvester_io_cardinals(self_, target):
            no_guard.add(p)
    for target in targets:
        target = target
        feed = harvester_feed_cardinal(self_, target)
        feed = feed
        if feed is None:
            continue
        if (
            affords_road
            and (feed in near)
            and self_.cost_grid[self_.idx(feed)] > 1
            and ct.can_build_road(feed)
        ):
            args = {}
            args["feed"] = auto_wrap_position(feed)
            log("guard_harvester_neighbours: ROAD on feed {feed} (prep step-off)", args)
            ct.build_road(feed)
            return None
        if not affords_guard:
            continue
        for d in DIR4:
            pos = target.add(d)
            if pos not in near:
                continue
            if pos in no_guard:
                continue
            if not needs_harvester_guard(self_, pos, target, no_guard):
                continue
            if place_harvester_guard(self_, ct, pos, target):
                return None
    return TaskRejected("nothing to guard around any visible harvester / claim")
