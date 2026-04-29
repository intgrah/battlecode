"""TangentBug — Bug2 with LOS shortcut post-processing, plan once."""

from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._planner import bug2_plan
from bench_nav.stepped.dp_step import dp_step
from bench_nav.types import PrecompCtx, Stepped


def _has_los(cost: list[int], w: int, h: int, a: int, b: int) -> bool:
    ax = a % w
    ay = a // w
    bx = b % w
    by = b // w
    dx = bx - ax
    if dx < 0:
        dx = -dx
    dy = by - ay
    if dy < 0:
        dy = -dy
    sx = 1 if ax < bx else -1
    sy = 1 if ay < by else -1
    err = dx - dy
    cx = ax
    cy = ay
    while True:
        if cx == bx and cy == by:
            return True
        e2 = err << 1
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
        if not (0 <= cx < w and 0 <= cy < h):
            return False
        if cost[cy * w + cx] >= INF:
            return False


def _bresenham(w: int, a: int, b: int) -> list[int]:
    ax = a % w
    ay = a // w
    bx = b % w
    by = b // w
    dx = bx - ax
    if dx < 0:
        dx = -dx
    dy = by - ay
    if dy < 0:
        dy = -dy
    sx = 1 if ax < bx else -1
    sy = 1 if ay < by else -1
    err = dx - dy
    out: list[int] = []
    cx = ax
    cy = ay
    while True:
        out.append(cy * w + cx)
        if cx == bx and cy == by:
            return out
        e2 = err << 1
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy


def _shortcut(cost: list[int], w: int, h: int, path: list[int]) -> list[int]:
    if len(path) <= 2:
        return path
    out: list[int] = [path[0]]
    i = 0
    n = len(path)
    while i < n - 1:
        j = i + 1
        best = i + 1
        while j < n:
            if _has_los(cost, w, h, path[i], path[j]):
                best = j
            else:
                break
            j += 1
        if best == i + 1:
            out.append(path[i + 1])
            i += 1
        else:
            line = _bresenham(w, path[i], path[best])
            out.extend(line[1:])
            i = best
    return out


class TangentBug(Stepped):
    REQUIRES = frozenset({COST})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.h = ctx.h
        self.n = ctx.n
        self.cost = ctx[COST]
        self._active_goal: int | None = None
        self._path_idx: list[int] = [-1] * ctx.n
        self._has_path: bool = False

    @override
    def step(self, pos: int, goal: int) -> int | None:
        if goal != self._active_goal:
            self._active_goal = goal
            self._path_idx[:] = [-1] * self.n
            raw = bug2_plan(self.cost, self.w, self.h, pos, goal)
            if raw is None:
                self._has_path = False
                return None
            for i, c in enumerate(_shortcut(self.cost, self.w, self.h, raw)):
                self._path_idx[c] = i
            self._has_path = True
        if not self._has_path:
            return None
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)
