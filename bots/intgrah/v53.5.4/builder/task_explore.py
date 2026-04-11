from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, INF, try_move

from builder.algorithms.astar import pathfind_move
from builder.helpers import try_move_with_build

if TYPE_CHECKING:
    from cambc import Controller

    from builder.state import State

__all__ = ["task_xplore"]


def _move_via_path(
    state: State, ct: Controller, target: Position, *, check_money: bool = True
) -> None:
    start = ct.get_position()
    next_pos = pathfind_move(state, ct, start, target)
    print(
        f"      explore: start={start} target={target} next={next_pos} ti={ct.get_global_resources()[0]}"
    )
    if next_pos is not None:
        if check_money and ct.get_global_resources()[0] < 75:
            dirs = DIR8
            state.rng.shuffle(dirs)
            my_pos = ct.get_position()
            moved = False
            for d in dirs:
                if try_move(ct, my_pos.add(d)):
                    moved = True
                    break
            print(f"      explore: low_ti moved={moved}")
        else:
            result = try_move_with_build(state, ct, next_pos)
            print(f"      explore: try_move_with_build={result}")
    else:
        print("      explore: no path")


def task_xplore(state: State, ct: Controller) -> None:
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
        ct.draw_indicator_dot(t, 255, 0, 255)
        _move_via_path(state, ct, t)
    else:
        ct.draw_indicator_dot(t, 10, 0, 10)
        _move_via_path(state, ct, t)
