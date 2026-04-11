from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8, try_move

from .helpers import find_path, try_move_with_build

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

__all__ = ["explore", "initial_explore"]


def _move_via_path(
    state: State, ct: Controller, target: Position, *, check_money: bool = True
) -> None:
    start = ct.get_position()
    path = find_path(state, ct, start, target)
    if path and len(path) > 1:
        next_pos = path[1]
        if check_money and ct.get_global_resources()[0] < 75:
            dirs = DIR8
            state.rng.shuffle(dirs)
            my_pos = ct.get_position()
            for d in dirs:
                if try_move(ct, my_pos.add(d)):
                    break
        else:
            try_move_with_build(state, ct, next_pos)


def _pick_frontier_target(state: State, ct: Controller) -> Position | None:
    w = state.w
    frontier = state.frontier
    if not frontier:
        return None
    my_pos = ct.get_position()
    mx, my = my_pos.x, my_pos.y
    best = -1
    best_dist = float("inf")
    for fi in frontier:
        if state.cost_grid[fi] == float("inf"):
            continue
        fx, fy = fi % w, fi // w
        d = (fx - mx) ** 2 + (fy - my) ** 2
        if d < best_dist:
            best_dist = d
            best = fi
    if best < 0:
        return None
    return Position(best % w, best // w)


def explore(state: State, ct: Controller) -> None:
    state.scout_age += 1
    m = state
    t = state.scout_target

    if (
        state.scout_age > 20
        or t is None
        or ct.get_position().distance_squared(t) < 3
        or m.get_cost(t) == float("inf")
        or (t and m._idx(t) not in state.frontier)
    ):
        ft = _pick_frontier_target(state, ct)
        if ft is not None:
            t = ft
        else:
            for _ in range(20):
                theta = state.rng.random() * 2 * math.pi
                candidate = Position(
                    ct.get_position().x + round(math.cos(theta) * state.scout_radius),
                    ct.get_position().y + round(math.sin(theta) * state.scout_radius),
                )
                if (
                    0 <= candidate.x < m.w
                    and 0 <= candidate.y < m.h
                    and m.get_cost(candidate) != float("inf")
                ):
                    t = candidate
                    break
                if state.scout_radius >= m.w / 2 or state.scout_radius >= m.h / 2:
                    state.scout_radius -= 1.0
            else:
                return

        state.scout_age = 0
        state.scout_target = t

    if t is not None:
        ct.draw_indicator_dot(t, 255, 0, 255)
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
        or m.get_cost(t) == float("inf")
    ):
        t = Position(-10, -10)
        while (
            t.x < 0
            or t.y < 0
            or t.x >= m.w
            or t.y >= m.h
            or m.get_cost(t) == float("inf")
        ):
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
        ct.draw_indicator_dot(t, 255, 0, 255)
        _move_via_path(state, ct, t)
    else:
        ct.draw_indicator_dot(t, 10, 0, 10)
        _move_via_path(state, ct, t)
