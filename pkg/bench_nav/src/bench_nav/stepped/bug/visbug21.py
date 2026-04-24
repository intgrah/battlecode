"""VisBug-21 — m-line sensor jumps, stepped."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
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


def _on_baseline(p: tuple[int, int], s: tuple[int, int], g: tuple[int, int]) -> bool:
    dx_t = g[0] - s[0]
    dy_t = g[1] - s[1]
    dx_c = p[0] - s[0]
    dy_c = p[1] - s[1]
    cross = abs(dy_c * dx_t - dx_c * dy_t)
    tol = max(abs(dx_t), abs(dy_t)) // 2
    if cross > tol:
        return False
    dot = dx_c * dx_t + dy_c * dy_t
    return dot > 0 and dist_sq(p, g) < dist_sq(s, g)


def _jump_along_mline(
    pos: tuple[int, int],
    start: tuple[int, int],
    goal: tuple[int, int],
    passable: Callable[[int, int], bool],
) -> tuple[int, int] | None:
    cur_d = dist_sq(pos, goal)
    best: tuple[tuple[int, int], int] | None = None
    for c in sensed_cells(pos):
        if c == pos or not _on_baseline(c, start, goal) or not passable(*c):
            continue
        d = dist_sq(c, goal)
        if d >= cur_d or not has_los(pos, c, passable):
            continue
        if best is None or d < best[1]:
            best = (c, d)
    return best[0] if best is not None else None


class VisBug21(Stepped):
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
        self._start_xy: tuple[int, int] = (0, 0)
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(
            pos=(0, 0), current_obstacle=(0, 0), obstacle_on_right=True
        )
        self._hit_dist_sq = 0
        self._follow_visited: set[tuple[tuple[int, int], tuple[int, int], bool]] = set()
        self._los_queue: list[tuple[int, int]] = []

    def _reset(self, p: tuple[int, int], g: tuple[int, int]) -> None:
        self._start_xy = p
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(pos=p, current_obstacle=p, obstacle_on_right=True)
        self._hit_dist_sq = dist_sq(p, g)
        self._follow_visited.clear()
        self._los_queue.clear()

    @override
    def step(self, pos: int, goal: int) -> int | None:
        w = self.w
        p = (pos % w, pos // w)
        g = (goal % w, goal // w)
        if goal != self._active_goal:
            self._active_goal = goal
            self._reset(p, g)
        if not self.passable(*p) or not self.passable(*g):
            return None
        if p == g:
            return pos
        if self._los_queue:
            nxt = self._los_queue.pop(0)
            return nxt[1] * w + nxt[0]

        if self._mode is _Mode.MOTION:
            target = _jump_along_mline(p, self._start_xy, g, self.passable)
            if target is not None:
                queue = bresenham(p, target)[1:]
                self._los_queue = queue[1:]
                first = queue[0]
                return first[1] * w + first[0]
            d = dir_to_goal(p, g)
            np = neighbour(p, d)
            if self.passable(*np):
                return np[1] * w + np[0]
            self._mode = _Mode.FOLLOW
            self._wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._hit_dist_sq = dist_sq(p, g)
            self._follow_visited.clear()
            self._follow_visited.add(
                (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
            )
            return pos
        # FOLLOW
        if dist_sq(p, g) <= 2 and self.passable(*g):
            self._mode = _Mode.MOTION
            return g[1] * w + g[0]
        self._wf.pos = p
        outcome = wall_follow_step(self._wf, self.passable, self.on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        np = self._wf.pos
        if _on_baseline(np, self._start_xy, g) and dist_sq(np, g) < self._hit_dist_sq:
            self._mode = _Mode.MOTION
        state = (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
        if state in self._follow_visited:
            return None
        self._follow_visited.add(state)
        return np[1] * w + np[0]
