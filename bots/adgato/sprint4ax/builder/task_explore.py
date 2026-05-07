from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, INF, try_move

from .helpers import find_next, try_move_with_road

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder, PosInt

__all__ = ["explore", "initial_explore"]


def _move_via_path(
    self: Builder, ct: Controller, target: PosInt, *, check_money: bool = True
) -> None:
    next_pos = find_next(self, ct, self.my_pos, [target])
    if next_pos:
        if check_money and ct.get_global_resources()[0] < 75:
            dirs = list(DIR8)
            self.rng.shuffle(dirs)
            my_pos = self.my_pos
            for d in dirs:
                if try_move(self, ct, my_pos + d):
                    break
        else:
            try_move_with_road(self, ct, next_pos)


def explore(self: Builder, ct: Controller) -> None:
    self.scout_age += 1
    m = self
    t = self.pos(self.scout_target)

    my_pos = self.pos(self.my_pos)

    if (
        self.scout_age > 20
        or t is None
        or (my_pos.x - t.x) ** 2 + (my_pos.y - t.y) ** 2 < 3
        or not m.is_passable(self._idx(t))
    ):
        t = Position(-10, -10)
        while (
            t.x < 0
            or t.y < 0
            or t.x >= m.w
            or t.y >= m.h
            or not m.is_passable(self._idx(t))
        ):
            theta = self.rng.random() * 2 * math.pi
            t = Position(
                my_pos.x + round(math.cos(theta) * self.scout_radius),
                my_pos.y + round(math.sin(theta) * self.scout_radius),
            )
            if self.scout_radius >= m.w / 2 or self.scout_radius >= m.h / 2:
                self.scout_radius -= 1.0

        self.scout_age = 0
        self.scout_target = self._idx(t)
        _move_via_path(self, ct, self._idx(t))
    else:
        _move_via_path(self, ct, self._idx(t))


def initial_explore(self: Builder, ct: Controller, vertical: int = 0) -> None:
    self.scout_initial_age += 1
    m = self
    t = self.pos(self.scout_initial_target)
    number_tries = 0

    my_pos = self.pos(self.my_pos)

    if (
        self.scout_initial_age > 10
        or t is None
        or (my_pos.x - t.x) ** 2 + (my_pos.y - t.y) ** 2 < 3
        or m.get_cost(self._idx(t)) == INF
    ):
        t = Position(-10, -10)
        while (
            t.x < 0
            or t.y < 0
            or t.x >= m.w
            or t.y >= m.h
            or m.get_cost(self._idx(t)) == INF
        ):
            up_down = self.rng.randint(0, 1)
            theta = self.rng.random() * math.pi / 2
            if not vertical:
                theta = theta + up_down * math.pi + math.pi / 4
            elif vertical is 1:
                theta = theta + up_down * math.pi - math.pi / 4
            else:
                theta = self.rng.random() * math.pi * 2
            if number_tries > 5:
                vertical = -1
            t = Position(
                my_pos.x + round(math.cos(theta) * self.scout_initial_radius),
                my_pos.y + round(math.sin(theta) * self.scout_initial_radius),
            )
            if (
                self.scout_initial_radius >= m.w / 2
                or self.scout_initial_radius >= m.h / 2
            ):
                self.scout_initial_radius -= 1.0
            number_tries += 1

        self.scout_initial_age = 0
        self.scout_initial_target = self._idx(t)
        _move_via_path(self, ct, self._idx(t))
    else:
        _move_via_path(self, ct, self._idx(t))
