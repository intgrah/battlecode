from __future__ import annotations

import heapq
import random
from typing import TYPE_CHECKING, Final

from cambc import Controller, Position
from util import DIR8_DELTA

if TYPE_CHECKING:
    from builder import Builder

from util import INF

_DIR8_DELTA = DIR8_DELTA.copy()
random.shuffle(_DIR8_DELTA)


class MoveHeapAstar:
    CPU_BUDGET: Final[int] = 1729
    TARGET_DRIFT_SQ: Final[int] = 25

    def __init__(self) -> None:
        self.w = 0
        self.h = 0
        self.pad_w = 0
        self.pad = 0
        self.dist: list[int] = []
        self.visited = bytearray()
        self.prev_visited = bytearray()
        self.q: list[tuple[float, int, Position]] = []
        self.finished = True
        self._no_path = False
        self._prev_no_path = False
        self.target: Position | None = None
        self.prev_target: Position | None = None

    def _init_grid(self, state: Builder) -> None:
        self.w, self.h = state.w, state.h
        self.pad_w = state.pad_w
        self.pad = state.pad
        pn = state.pad_w * state.pad_h
        self.dist = [INF] * pn
        self._visited_reset = bytes((pn + 7) // 8)

    def _reset(self, state: Builder) -> None:
        pn = state.pad_w * state.pad_h
        if len(self.dist) != pn:
            self._init_grid(state)
        self._no_path = False
        self.visited = bytearray(self._visited_reset)
        self.q = []

    def _extract_path(
        self,
        state: Builder,
        start: Position,
        target: Position,
    ) -> list[Position]:
        cost = state.cost_grid
        pw = self.pad_w
        pad = self.pad
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = INF
            best = current
            ci = (current.y + pad) * pw + (current.x + pad)
            for dx, dy in _DIR8_DELTA:
                nx = current.x + dx
                ny = current.y + dy
                if not (0 <= nx < self.w and 0 <= ny < self.h):
                    continue
                idx = ci + dy * pw + dx
                if (self.prev_visited[idx >> 3] & (1 << (idx & 0b111))) and cost[
                    idx
                ] < INF:
                    d = self.dist[idx]
                    if d < best_dist:
                        best_dist = d
                        best = Position(nx, ny)
            current = best
        path.append(target)
        return path

    def _run(
        self,
        state: Builder,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> bool:
        cost = state.cost_grid
        bfs_dist = state.bfs_dist
        w = self.w
        pw = self.pad_w
        pad = self.pad
        w_bound = self.w
        h_bound = self.h
        dist = self.dist
        visited = self.visited
        q = self.q

        gi = (goal.y + pad) * pw + (goal.x + pad)
        dist[gi] = 0
        visited[gi >> 3] |= 1 << (gi & 7)
        counter = 0
        heapq.heappush(q, (0, counter, goal))
        counter += 1

        sx, sy = start.x, start.y
        while q:
            _, _, current = heapq.heappop(q)
            if current == start:
                return True
            if ct.get_cpu_time_elapsed() > MoveHeapAstar.CPU_BUDGET:
                return False

            ci = (current.y + pad) * pw + (current.x + pad)
            cur_dist = dist[ci]
            for dx, dy in _DIR8_DELTA:
                nx = current.x + dx
                ny = current.y + dy
                if nx < 0 or nx >= w_bound or ny < 0 or ny >= h_bound:
                    continue
                idx = ci + dy * pw + dx
                if visited[idx >> 3] & (1 << (idx & 0b111)):
                    continue
                move_cost = cost[idx]
                if move_cost >= INF:
                    continue
                visited[idx >> 3] |= 1 << (idx & 0b111)
                new_dist = cur_dist + move_cost
                dist[idx] = new_dist
                bd = bfs_dist[ny * w + nx]
                if bd < INF:
                    f = new_dist + bd
                else:
                    f = new_dist + max(abs(ny - sy), abs(nx - sx))
                heapq.heappush(q, (f, counter, Position(nx, ny)))
                counter += 1

        self._no_path = True
        return True

    def search(
        self,
        state: Builder,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        if (
            self.finished
            or self.target is None
            or target.distance_squared(self.target) > MoveHeapAstar.TARGET_DRIFT_SQ
        ):
            self._reset(state)
        else:
            target = self.target

        self.target = target
        self.finished = self._run(state, ct, start, target)

        if self.finished:
            self.prev_visited = self.visited
            self.prev_target = target
            self._prev_no_path = self._no_path

        if self.prev_target is None:
            return None
        diff = target.distance_squared(self.prev_target)
        if diff <= MoveHeapAstar.TARGET_DRIFT_SQ and diff < start.distance_squared(
            target,
        ):
            if self._no_path:
                return None
            return self._extract_path(state, start, target)
        return None

    def search_blocked(
        self,
        state: Builder,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        cost = state.cost_grid
        pw = state.pad_w
        pad = state.pad
        saved: list[tuple[int, int]] = []
        for pos in state.nearby_tiles:
            if pos in state.all_bots and pos != start:
                idx = (pos.y + pad) * pw + (pos.x + pad)
                saved.append((idx, cost[idx]))
                cost[idx] = INF
        result = self.search(state, ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result

    @property
    def no_path(self) -> bool:
        return self._prev_no_path


move_search = MoveHeapAstar()


def pathfind_blocked(
    state: Builder,
    ct: Controller,
    start: Position,
    goal: Position,
) -> list[Position] | None:
    return move_search.search_blocked(state, ct, start, goal)
