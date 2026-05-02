"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/split_before_sentinel.py`.

Upgrade the conveyor immediately upstream of a friendly sentinel into
a splitter, forking the offensive chain into three outputs.
"""
from __future__ import annotations

from cambc import Direction, EntityType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import can_afford, make_move, try_place
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.constants import MAX_WIDTH
from util.directions import DIR4, delta_to_dir

def feeder_delta(self_, pos):
    """
    If `pos` has exactly one cardinal friendly feeder, return the
    DIR4 direction `d` such that `pos - d.delta() == feeder_pos`. This
    is the splitter's forward direction when placed at `pos`: input
    side = `pos + d.opposite()` = `feeder_pos`.
    """
    feeders = self_.in_edges[int(pos.y) * 50 + int(pos.x)]
    if len(feeders) != 1:
        return None
    feeder = feeders[0]
    dx = pos.x - feeder.x
    dy = pos.y - feeder.y
    d = delta_to_dir(dx, dy)
    if not (d in DIR4):
        return None
    return d

def split_before_sentinel(self_, ct):
    if not can_afford(self_, EntityType.SPLITTER):
        return TaskRejected("cannot afford SPLITTER")
    best_split: Position | None = None
    best_dir: Direction | None = None
    best_dist = 1 << 30
    for sent_pos in self_.nearby_buildings:
        if not (self_.building_kind[self_.idx(sent_pos)] == EntityType.SENTINEL and self_.building_team[self_.idx(sent_pos)] == self_.my_team):
            continue
        feeders = list(self_.in_edges[int(sent_pos.y) * 50 + int(sent_pos.x)])
        for split_pos in feeders:
            if not (self_.building_kind[self_.idx(split_pos)] == EntityType.CONVEYOR and self_.building_team[self_.idx(split_pos)] == self_.my_team):
                continue
            uid = self_.all_bots.get(split_pos)
            if uid is not None and (uid != self_.my_id):
                continue
            sd = feeder_delta(self_, split_pos)
            sd = sd
            if sd is None:
                continue
            d = self_.my_pos.distance_squared(split_pos)
            if d < best_dist:
                best_dist = d
                best_split = split_pos
                best_dir = sd
    best_split = best_split
    best_dir = best_dir
    if best_split is None or best_dir is None:
        return TaskRejected("no friendly sentinel with a splittable upstream conveyor")
    if self_.my_pos.distance_squared(best_split) <= 2:
        try_place(self_, ct, EntityType.SPLITTER, best_split, best_dir, True)
        return None
    make_move(self_, ct, best_split)
    return None
