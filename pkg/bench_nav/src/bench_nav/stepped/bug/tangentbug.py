"""TangentBug — stepped."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from math import sqrt
from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._common import (
    WallFollowState,
    WallStepOutcome,
    bresenham,
    dir_to_goal,
    dist_sq,
    has_los,
    make_passable_closures,
    neighbour,
    sensed_cells,
    wall_follow_step,
)
from bench_nav.types import PrecompCtx, Stepped


class _Mode(Enum):
    MOTION = 0
    FOLLOW = 1


def _distf(a: tuple[int, int], b: tuple[int, int]) -> float:
    return sqrt(dist_sq(a, b))


def _best_heuristic_subgoal(
    pos: tuple[int, int], goal: tuple[int, int], passable: Callable[[int, int], bool]
) -> tuple[tuple[int, int], float] | None:
    best: tuple[tuple[int, int], float] | None = None
    for c in sensed_cells(pos):
        if c == pos or not passable(*c) or not has_los(pos, c, passable):
            continue
        h = _distf(pos, c) + _distf(c, goal)
        if best is None or h < best[1]:
            best = (c, h)
    return best


def _best_visible_boundary(
    pos: tuple[int, int], goal: tuple[int, int], passable: Callable[[int, int], bool]
) -> tuple[tuple[int, int], float] | None:
    best: tuple[tuple[int, int], float] | None = None
    for c in sensed_cells(pos):
        if not passable(*c) or not has_los(pos, c, passable):
            continue
        is_boundary = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                if not passable(c[0] + dx, c[1] + dy):
                    is_boundary = True
                    break
            if is_boundary:
                break
        if not is_boundary:
            continue
        d = _distf(c, goal)
        if best is None or d < best[1]:
            best = (c, d)
    return best


class TangentBug(Stepped):
    REQUIRES = frozenset({COST})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.cost = ctx[COST]
        self.passable, self.on_map = make_passable_closures(
            ctx.w, ctx.h, self.cost, INF
        )
        self._active_goal: int | None = None
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(
            pos=(0, 0), current_obstacle=(0, 0), obstacle_on_right=True
        )
        self._d_followed = float("inf")
        self._follow_visited: set[tuple[tuple[int, int], tuple[int, int], bool]] = set()
        self._los_queue: list[tuple[int, int]] = []

    def _reset(self, p: tuple[int, int]) -> None:
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(pos=p, current_obstacle=p, obstacle_on_right=True)
        self._d_followed = float("inf")
        self._follow_visited.clear()
        self._los_queue.clear()

    def _move_one_toward(
        self, cur: tuple[int, int], target: tuple[int, int]
    ) -> tuple[int, int] | None:
        dx = (target[0] > cur[0]) - (target[0] < cur[0])
        dy = (target[1] > cur[1]) - (target[1] < cur[1])
        if dx == 0 and dy == 0:
            return None
        np = (cur[0] + dx, cur[1] + dy)
        return np if self.passable(*np) else None

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            self._reset(p)
        if not self.passable(*p) or not self.passable(*g):
            return None
        if p == g:
            return pos

        if self._los_queue:
            nxt = self._los_queue.pop(0)
            return nxt[1] * w + nxt[0]

        if self._mode is _Mode.MOTION:
            if has_los(p, g, self.passable):
                np = self._move_one_toward(p, g)
                return (np[1] * w + np[0]) if np is not None else pos
            d_pos_goal = _distf(p, g)
            sub = _best_heuristic_subgoal(p, g, self.passable)
            if sub is not None and sub[1] < d_pos_goal:
                np = self._move_one_toward(p, sub[0])
                if np is not None:
                    return np[1] * w + np[0]
            self._mode = _Mode.FOLLOW
            d = dir_to_goal(p, g)
            self._wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._d_followed = d_pos_goal
            self._follow_visited.clear()
            self._follow_visited.add(
                (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
            )
            return pos
        # FOLLOW
        bb = _best_visible_boundary(p, g, self.passable)
        if bb is not None and bb[1] < self._d_followed:
            self._mode = _Mode.MOTION
            queue = bresenham(p, bb[0])[1:]
            if not queue:
                return pos
            self._los_queue = queue[1:]
            first = queue[0]
            return first[1] * w + first[0]
        self._wf.pos = p
        outcome = wall_follow_step(self._wf, self.passable, self.on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        np = self._wf.pos
        cur_d = _distf(np, g)
        self._d_followed = min(self._d_followed, cur_d)
        state = (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
        if state in self._follow_visited:
            return None
        self._follow_visited.add(state)
        return np[1] * w + np[0]
