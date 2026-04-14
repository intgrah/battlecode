from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, INF, try_move

from builder.algorithms.astar import pathfind_blocked
from builder.helpers import try_move_with_road

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["explore", "initial_explore"]


def _move_via_path(
    self: Builder,
    ct: Controller,
    target: Position,
    *,
    check_money: bool = True,
) -> None:
    start = ct.get_position()
    path = pathfind_blocked(self, ct, start, target)
    if path and len(path) > 1:
        next_pos = path[1]
        if check_money and ct.get_global_resources()[0] < 75:
            dirs = DIR8
            self.rng.shuffle(dirs)
            my_pos = ct.get_position()
            for d in dirs:
                if try_move(ct, my_pos.add(d)):
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
        or (ct.get_position().x - t.x) ** 2 + (ct.get_position().y - t.y) ** 2 < 3
        or m.get_cost(t) == INF
    ):
        t = Position(-10, -10)
        while t.x < 0 or t.y < 0 or t.x >= m.w or t.y >= m.h or m.get_cost(t) == INF:
            theta = self.rng.random() * 2 * math.pi
            t = Position(
                ct.get_position().x + round(math.cos(theta) * self.scout_radius),
                ct.get_position().y + round(math.sin(theta) * self.scout_radius),
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


def initial_explore(self: Builder, ct: Controller, vertical: int = 0) -> None:
    self.scout_initial_age += 1
    m = self
    t = self.scout_initial_target
    number_tries = 0

    if (
        self.scout_initial_age > 10
        or t is None
        or (ct.get_position().x - t.x) ** 2 + (ct.get_position().y - t.y) ** 2 < 3
        or m.get_cost(t) == INF
    ):
        t = Position(-10, -10)
        while t.x < 0 or t.y < 0 or t.x >= m.w or t.y >= m.h or m.get_cost(t) == INF:
            up_down = self.rng.randint(0, 1)
            theta = self.rng.random() * math.pi / 2
            if vertical == 0:
                theta = theta + up_down * math.pi + math.pi / 4
            elif vertical == 1:
                theta = theta + up_down * math.pi - math.pi / 4
            else:
                theta = self.rng.random() * math.pi * 2
            if number_tries > 5:
                vertical = -1
            t = Position(
                ct.get_position().x
                + round(math.cos(theta) * self.scout_initial_radius),
                ct.get_position().y
                + round(math.sin(theta) * self.scout_initial_radius),
            )
            if (
                self.scout_initial_radius >= m.w / 2
                or self.scout_initial_radius >= m.h / 2
            ):
                self.scout_initial_radius -= 1.0
            number_tries += 1

        self.scout_initial_age = 0
        self.scout_initial_target = t
        ct.draw_indicator_dot(t, 255, 0, 255)
        _move_via_path(self, ct, t)
    else:
        ct.draw_indicator_dot(t, 10, 0, 10)
        _move_via_path(self, ct, t)
