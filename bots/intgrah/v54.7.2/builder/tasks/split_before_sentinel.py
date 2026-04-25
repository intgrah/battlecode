"""Upgrade the conveyor immediately upstream of a friendly sentinel into
a splitter, forking the offensive chain into three outputs: one toward
the sentinel (consumed there), two as fresh dangling ends. Splitter
direction = `split_pos - feeder_pos` so the input side lands exactly on
the existing feeder. Skip if the feeder offset isn't a DIR4 unit (e.g.
bridge feeders) — splitter input must be cardinally adjacent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingConveyor, BuildingSentinel
from cambc import EntityType
from util.constants import MAX_WIDTH
from util.directions import DELTA_TO_DIR, DIR4

from builder.helpers import can_afford, make_move, try_place
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Direction, Position

    from builder import Builder


class TaskRejectedNoSplitTargetError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no friendly sentinel with a splittable upstream conveyor"


class TaskRejectedCannotAffordSplitterError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "cannot afford SPLITTER"


def _feeder_delta(self: Builder, pos: Position) -> Direction | None:
    """If `pos` has exactly one cardinal friendly feeder, return the
    DIR4 direction `d` such that `pos - d.delta() == feeder_pos`. This
    is the splitter's forward direction when placed at `pos`: input
    side = `pos + d.opposite()` = feeder_pos.
    """
    feeders = self.in_edges[pos.y * MAX_WIDTH + pos.x]
    if len(feeders) != 1:
        return None
    feeder = feeders[0]
    dx, dy = pos.x - feeder.x, pos.y - feeder.y
    if (dx, dy) not in DELTA_TO_DIR:
        return None
    d = DELTA_TO_DIR[(dx, dy)]
    if d not in DIR4:
        return None
    return d


def split_before_sentinel(self: Builder, ct: Controller) -> None:
    if not can_afford(self, EntityType.SPLITTER):
        raise TaskRejectedCannotAffordSplitterError

    best_split: Position | None = None
    best_dir: Direction | None = None
    best_dist = 1 << 30
    for sent_pos in self.nearby_buildings:
        b = self.get_building(sent_pos)
        if not isinstance(b, BuildingSentinel) or b.team != self.my_team:
            continue
        feeders = self.in_edges[sent_pos.y * MAX_WIDTH + sent_pos.x]
        for split_pos in feeders:
            sb = self.get_building(split_pos)
            if not isinstance(sb, BuildingConveyor) or sb.team != self.my_team:
                continue
            if split_pos in self.all_bots and self.all_bots[split_pos] != self.my_id:
                continue
            sd = _feeder_delta(self, split_pos)
            if sd is None:
                continue
            d = self.my_pos.distance_squared(split_pos)
            if d < best_dist:
                best_dist = d
                best_split = split_pos
                best_dir = sd

    if best_split is None or best_dir is None:
        raise TaskRejectedNoSplitTargetError

    if self.my_pos.distance_squared(best_split) <= 2:
        try_place(self, ct, EntityType.SPLITTER, best_split, best_dir)
        return
    make_move(self, ct, best_split)
