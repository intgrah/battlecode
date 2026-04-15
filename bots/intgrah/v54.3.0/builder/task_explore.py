from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, INF

from builder.helpers import make_move, try_move_dir

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["explore"]


def explore(self: Builder, ct: Controller) -> None:
    self.scout_age += 1

    if (
        self.scout_age > 20
        or self.scout_target is None
        or self.my_pos.distance_squared(self.scout_target) < 3
        or self.get_cost(self.scout_target) == INF
    ):
        t = Position(-1, -1)
        while (
            t.x < 0
            or t.y < 0
            or t.x >= self.w
            or t.y >= self.h
            or self.get_cost(t) == INF
        ):
            theta = self.rng.random() * 2 * math.pi
            t = Position(
                self.my_pos.x + round(math.cos(theta) * self.scout_radius),
                self.my_pos.y + round(math.sin(theta) * self.scout_radius),
            )
            if self.scout_radius >= self.w / 2 or self.scout_radius >= self.h / 2:
                self.scout_radius -= 1.0

        self.scout_age = 0
        self.scout_target = t

    if self.ti < 75:
        dir8 = DIR8.copy()
        self.rng.shuffle(dir8)
        for d in dir8:
            if try_move_dir(ct, d):
                break
    else:
        make_move(self, ct, self.scout_target)
