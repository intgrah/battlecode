from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, INF, try_move

from .helpers import find_next, try_move_with_road

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

__all__ = ["explore", "initial_explore"]


def _move_via_path(
    state: State, ct: Controller, target: Position, *, check_money: bool = True
) -> None:
    start = ct.get_position()
    next_pos = find_next(state, ct, start, [target])
    if next_pos:
        if check_money and ct.get_global_resources()[0] < 75:
            dirs = DIR8
            state.rng.shuffle(dirs)
            my_pos = ct.get_position()
            for d in dirs:
                if try_move(ct, my_pos.add(d)):
                    break
        else:
            try_move_with_road(ct, next_pos)


def explore(state: State, ct: Controller) -> None:
    state.scout_age += 1
    m = state
    t = state.scout_target

    if (
        state.scout_age > 20
        or t is None
        or (ct.get_position().x - t.x) ** 2 + (ct.get_position().y - t.y) ** 2 < 3
        or m.get_cost(t) == INF
    ):
        t = Position(-10, -10)
        while t.x < 0 or t.y < 0 or t.x >= m.w or t.y >= m.h or m.get_cost(t) == INF:
            theta = state.rng.random() * 2 * math.pi
            t = Position(
                ct.get_position().x + round(math.cos(theta) * state.scout_radius),
                ct.get_position().y + round(math.sin(theta) * state.scout_radius),
            )
            if state.scout_radius >= m.w / 2 or state.scout_radius >= m.h / 2:
                state.scout_radius -= 1.0

        state.scout_age = 0
        state.scout_target = t
        _move_via_path(state, ct, t)
    else:
        _move_via_path(state, ct, t)


def initial_explore(state: State, ct: Controller, vertical: int = 0) -> None:
    state.scout_initial_age += 1
    m = state
    t = state.scout_initial_target
    number_tries = 0

    if (
        state.scout_initial_age > 10
        or t is None
        or (ct.get_position().x - t.x) ** 2 + (ct.get_position().y - t.y) ** 2 < 3
        or m.get_cost(t) == INF
    ):
        t = Position(-10, -10)
        while t.x < 0 or t.y < 0 or t.x >= m.w or t.y >= m.h or m.get_cost(t) == INF:
            up_down = state.rng.randint(0, 1)
            theta = state.rng.random() * math.pi / 2
            if vertical == 0:
                theta = theta + up_down * math.pi + math.pi / 4
            elif vertical == 1:
                theta = theta + up_down * math.pi - math.pi / 4
            else:
                theta = state.rng.random() * math.pi * 2
            if number_tries > 5:
                vertical = -1
            t = Position(
                ct.get_position().x
                + round(math.cos(theta) * state.scout_initial_radius),
                ct.get_position().y
                + round(math.sin(theta) * state.scout_initial_radius),
            )
            if (
                state.scout_initial_radius >= m.w / 2
                or state.scout_initial_radius >= m.h / 2
            ):
                state.scout_initial_radius -= 1.0
            number_tries += 1

        state.scout_initial_age = 0
        state.scout_initial_target = t
        _move_via_path(state, ct, t)
    else:
        _move_via_path(state, ct, t)
