"""LookaheadBug — Bug0 with greedy lookahead, plan once."""

from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.stepped.bug._planner import DX, DY, dir_to
from bench_nav.stepped.dp_step import dp_step
from bench_nav.types import AlgoName, PrecompCtx, Stepped


def _lookahead_plan(
    cost: list[int], w: int, h: int, si: int, gi: int
) -> list[int] | None:
    if cost[si] >= INF or cost[gi] >= INF:
        return None
    safety_cap = 4 * w * h + 16
    path: list[int] = [si]
    pos = si
    gx = gi % w
    gy = gi // w
    follow = False
    wox = 0
    woy = 0
    on_right = 0
    hit_d = 0
    while pos != gi:
        if len(path) > safety_cap:
            return None
        px = pos % w
        py = pos // w
        if not follow:
            # Pick best of 8 neighbours by squared distance.
            best_d = (px - gx) * (px - gx) + (py - gy) * (py - gy)
            best_nx = px
            best_ny = py
            for di in range(8):
                nx = px + DX[di]
                ny = py + DY[di]
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if cost[ny * w + nx] >= INF:
                    continue
                ddx = nx - gx
                ddy = ny - gy
                dd = ddx * ddx + ddy * ddy
                if dd < best_d:
                    best_d = dd
                    best_nx = nx
                    best_ny = ny
            if best_nx == px and best_ny == py:
                follow = True
                d = dir_to(px, py, gx, gy)
                wox = px + DX[d]
                woy = py + DY[d]
                on_right = 0
                hit_d = (px - gx) * (px - gx) + (py - gy) * (py - gy)
                continue
            pos = best_ny * w + best_nx
            path.append(pos)
            continue
        # Wall-follow with greedy escape.
        d = dir_to(px, py, gx, gy)
        nx = px + DX[d]
        ny = py + DY[d]
        if 0 <= nx < w and 0 <= ny < h and cost[ny * w + nx] < INF:
            ddx = nx - gx
            ddy = ny - gy
            if ddx * ddx + ddy * ddy < hit_d:
                follow = False
                pos = ny * w + nx
                path.append(pos)
                continue
        odx = wox - px
        ody = woy - py
        sox = (odx > 0) - (odx < 0)
        soy = (ody > 0) - (ody < 0)
        if sox == 0:
            direction = 0 if soy < 0 else 4
        elif sox > 0:
            direction = 1 if soy < 0 else (2 if soy == 0 else 3)
        else:
            direction = 7 if soy < 0 else (6 if soy == 0 else 5)
        moved = False
        for _ in range(8):
            direction = (direction + 7) & 7 if on_right else (direction + 1) & 7
            ndx2 = DX[direction]
            ndy2 = DY[direction]
            nx2 = px + ndx2
            ny2 = py + ndy2
            on_map = 0 <= nx2 < w and 0 <= ny2 < h
            if on_map and cost[ny2 * w + nx2] < INF:
                pos = ny2 * w + nx2
                path.append(pos)
                moved = True
                break
            if on_map:
                wox = nx2
                woy = ny2
            else:
                return None
        if not moved:
            return None
    return path


class LookaheadBug(Stepped):
    NAME = AlgoName("bug-lookahead")
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
            raw = _lookahead_plan(self.cost, self.w, self.h, pos, goal)
            if raw is None:
                self._has_path = False
                return None
            for i, c in enumerate(raw):
                self._path_idx[c] = i
            self._has_path = True
        if not self._has_path:
            return None
        return dp_step(self.w, self.cost, self.h, pos, self._path_idx)
