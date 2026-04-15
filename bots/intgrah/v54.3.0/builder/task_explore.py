from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, INF

from builder.algorithms.astar import pathfind_blocked
from builder.helpers import try_move_dir, try_move_with_road

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["explore"]


def _move_via_path(
    self: Builder,
    ct: Controller,
    target: Position,
    *,
    check_money: bool = True,
) -> None:
    path = pathfind_blocked(self, ct, self.my_pos, target)
    if path and len(path) > 1:
        next_pos = path[1]
        if check_money and self.ti < 75:
            dirs = DIR8
            self.rng.shuffle(dirs)
            for d in dirs:
                if try_move_dir(ct, d):
                    break
        else:
            try_move_with_road(self, ct, next_pos)


def explore(self: Builder, ct: Controller) -> None:
    self.scout_age += 1
    m = self
    t = self.scout_target

    if (
        self.scout_age > 20
        or t is None
        or (self.my_pos.x - t.x) ** 2 + (self.my_pos.y - t.y) ** 2 < 3
        or m.get_cost(t) == INF
    ):
        t = Position(-10, -10)
        while t.x < 0 or t.y < 0 or t.x >= m.w or t.y >= m.h or m.get_cost(t) == INF:
            theta = self.rng.random() * 2 * math.pi
            t = Position(
                self.my_pos.x + round(math.cos(theta) * self.scout_radius),
                self.my_pos.y + round(math.sin(theta) * self.scout_radius),
            )
            if self.scout_radius >= m.w / 2 or self.scout_radius >= m.h / 2:
                self.scout_radius -= 1.0

        self.scout_age = 0
        self.scout_target = t
        ct.draw_indicator_dot(t, 255, 0, 255)
        _move_via_path(self, ct, t)
    else:
        ct.draw_indicator_dot(t, 10, 0, 10)
        _move_via_path(self, ct, t)
