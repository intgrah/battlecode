"""Memory+A* — stepped.

Structurally identical to Memory+BFS but expands cells by f = g + h
(Chebyshev), so fewer expansions reach the same depth; same expansion
budget buys a longer effective horizon.
"""

from __future__ import annotations

import heapq
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

_EXPAND_BUDGET = 500
_DIST_INF = 65535
_DIRS8: tuple[tuple[int, int], ...] = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


class _Mode(Enum):
    MOTION = 0
    CIRCUMNAV = 1
    RETURN_TO_LEAVE = 2


class MemAstar(Stepped):
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
        self._best_leave: tuple[int, int] = (0, 0)
        self._best_leave_dist_sq = 0
        self._global_min_dist_sq = 0
        self._follow_visited: set[tuple[tuple[int, int], tuple[int, int], bool]] = set()
        self._los_queue: list[tuple[int, int]] = []
        n = ctx.w * ctx.h
        self._pnb: list[list[int]] = [[] for _ in range(n)]
        self._discovered = bytearray(n)
        self._g_arr: list[int] = [_DIST_INF] * n

    def _reset(self, p: tuple[int, int], g: tuple[int, int]) -> None:
        w, h = self.w, self.h
        n = w * h
        self._mode = _Mode.MOTION
        self._wf = WallFollowState(pos=p, current_obstacle=p, obstacle_on_right=True)
        self._best_leave = p
        self._best_leave_dist_sq = dist_sq(p, g)
        self._global_min_dist_sq = dist_sq(p, g)
        self._follow_visited.clear()
        self._los_queue.clear()
        pnb = self._pnb
        for i in range(n):
            pnb[i] = []
        for y in range(h):
            for x in range(w):
                i = y * w + x
                row = pnb[i]
                for dx, dy in _DIRS8:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        row.append(ny * w + nx)
        self._discovered = bytearray(n)

    def _sense(self, cur_pos: tuple[int, int]) -> None:
        w, h = self.w, self.h
        cost = self.cost
        discovered = self._discovered
        pnb = self._pnb
        for c in sensed_cells(cur_pos):
            x, y = c
            if not (0 <= x < w and 0 <= y < h):
                continue
            i = y * w + x
            if discovered[i]:
                continue
            discovered[i] = 1
            if cost[i] >= INF:
                for dx, dy in _DIRS8:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if i in pnb[ni]:
                            pnb[ni].remove(i)
                pnb[i].clear()

    def _try_astar_step(
        self, cur_pos: tuple[int, int], goal: tuple[int, int], threshold: int
    ) -> tuple[int, int] | None:
        w = self.w
        n = w * self.h
        pnb = self._pnb
        g_arr = self._g_arr
        gx, gy = goal[0], goal[1]

        def heur(i: int) -> int:
            nx, ny = i % w, i // w
            return max(abs(nx - gx), abs(ny - gy))

        pos_idx = cur_pos[1] * w + cur_pos[0]
        for i in range(n):
            g_arr[i] = _DIST_INF
        g_arr[pos_idx] = 0
        heap: list[tuple[int, int]] = [(heur(pos_idx), pos_idx)]
        expansions = 0
        best_idx: int | None = None
        best_d = threshold
        reached_goal = False
        goal_idx = goal[1] * w + goal[0]

        while heap:
            f, node = heapq.heappop(heap)
            node_g = g_arr[node]
            if node_g == _DIST_INF:
                continue
            if f > node_g + heur(node):
                continue
            expansions += 1
            if expansions > _EXPAND_BUDGET:
                break
            if node == goal_idx:
                reached_goal = True
                best_idx = node
                break
            nx, ny = node % w, node // w
            dx = nx - gx
            dy = ny - gy
            d = dx * dx + dy * dy
            if d < best_d:
                best_d = d
                best_idx = node
            g_new = node_g + 1
            for ni in pnb[node]:
                if g_new < g_arr[ni]:
                    g_arr[ni] = g_new
                    heapq.heappush(heap, (g_new + heur(ni), ni))

        if best_idx is None:
            return None
        cur = best_idx
        while g_arr[cur] > 1:
            cur_g = g_arr[cur]
            next_cell: int | None = None
            for ni in pnb[cur]:
                if g_arr[ni] == cur_g - 1:
                    next_cell = ni
                    break
            if next_cell is None:
                return None
            cur = next_cell
        if g_arr[cur] == _DIST_INF or cur == pos_idx:
            return None
        first_step = (cur % w, cur // w)
        if not reached_goal and dist_sq(first_step, goal) >= threshold:
            return None
        return first_step

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
        self._sense(p)
        if has_los(p, g, self.passable):
            queue = bresenham(p, g)[1:]
            if queue:
                self._los_queue = queue[1:]
                first = queue[0]
                return first[1] * w + first[0]

        threshold = (
            dist_sq(p, g)
            if self._mode is _Mode.MOTION
            else min(self._global_min_dist_sq, self._best_leave_dist_sq)
        )
        astar_step = self._try_astar_step(p, g, threshold)
        if astar_step is not None:
            d2 = dist_sq(astar_step, g)
            self._global_min_dist_sq = min(self._global_min_dist_sq, d2)
            if self._mode is not _Mode.MOTION:
                self._mode = _Mode.MOTION
                self._follow_visited.clear()
            return astar_step[1] * w + astar_step[0]

        if self._mode is _Mode.MOTION:
            d = dir_to_goal(p, g)
            np = neighbour(p, d)
            if self.passable(*np):
                d2 = dist_sq(np, g)
                self._global_min_dist_sq = min(self._global_min_dist_sq, d2)
                return np[1] * w + np[0]
            self._mode = _Mode.CIRCUMNAV
            self._wf = WallFollowState(
                pos=p,
                current_obstacle=neighbour(p, d),
                obstacle_on_right=True,
            )
            self._best_leave = p
            self._best_leave_dist_sq = dist_sq(p, g)
            self._follow_visited.clear()
            self._follow_visited.add(
                (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
            )
            return pos
        if self._mode is _Mode.CIRCUMNAV:
            self._wf.pos = p
            outcome = wall_follow_step(self._wf, self.passable, self.on_map)
            if outcome is WallStepOutcome.SURROUNDED:
                return None
            np = self._wf.pos
            d2 = dist_sq(np, g)
            if d2 < self._best_leave_dist_sq:
                self._best_leave = np
                self._best_leave_dist_sq = d2
            state = (
                self._wf.pos,
                self._wf.current_obstacle,
                self._wf.obstacle_on_right,
            )
            if state in self._follow_visited:
                if self._best_leave_dist_sq >= self._global_min_dist_sq:
                    return None
                self._global_min_dist_sq = self._best_leave_dist_sq
                self._mode = _Mode.RETURN_TO_LEAVE
                self._follow_visited.clear()
                self._follow_visited.add(state)
            else:
                self._follow_visited.add(state)
            return np[1] * w + np[0]
        # RETURN_TO_LEAVE
        if p == self._best_leave:
            self._mode = _Mode.MOTION
            return pos
        self._wf.pos = p
        outcome = wall_follow_step(self._wf, self.passable, self.on_map)
        if outcome is WallStepOutcome.SURROUNDED:
            return None
        np = self._wf.pos
        state = (self._wf.pos, self._wf.current_obstacle, self._wf.obstacle_on_right)
        if state in self._follow_visited:
            return None
        self._follow_visited.add(state)
        return np[1] * w + np[0]
