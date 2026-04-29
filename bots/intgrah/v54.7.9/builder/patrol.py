from __future__ import annotations

from typing import TYPE_CHECKING

from builder.helpers import make_move

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


PATROL_RANGE = 4


def run_patrol(self: Builder, ct: Controller) -> bool:
    """Priority-queue patrol. Targets are populated by
    `update_patrol_queue` from harvesters/foundries/active conveyors. The
    head is dropped once it's in vision AND a friendly builder is already
    covering it; a fresh head is then picked from the highest
    age-times-priority entry.
    """
    if self.patrol_head is not None and ct.is_in_vision(self.patrol_head):
        if self.my_pos.distance_squared(self.patrol_head) <= PATROL_RANGE:
                self.patrol_head = None
        else:
            for friend in self.friendly_bots:
                if friend.distance_squared(self.patrol_head) <= PATROL_RANGE:
                    self.patrol_head = None
                    break

    if self.patrol_head is None and self.patrol_queue:
        rnd = self.round
        self.patrol_head = max(
            self.patrol_queue,
            key=lambda v: (rnd - v[1]) * v[2],
        )[0]

    if self.patrol_head is not None:
        make_move(self, ct, self.patrol_head)

    return bool(self.patrol_queue)
