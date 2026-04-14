from __future__ import annotations

import heapq
import random
from typing import TYPE_CHECKING, Final

from cambc import Controller, Position
from util import DIR8_DELTA

if TYPE_CHECKING:
    from builder import Builder

from util import INF

_TARGET_DRIFT_SQ: Final[int] = 25
_CPU_BUDGET: Final[int] = 1729

_DIR8_DELTA = DIR8_DELTA.copy()
random.shuffle(_DIR8_DELTA)


class MoveHeapAstar:
    def __init__(self) -> None:
        self._w = 0
        self._h = 0
        self._pw = 0
        self._pad = 0
        self._dist: list[int] = []
        self._visited = bytearray()
        self._prev_visited = bytearray()
        self._q: list[tuple[float, int, Position]] = []
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _init_grid(self, state: Builder) -> None:
        self._w, self._h = state.w, state.h
        self._pw = state.pad_w
        self._pad = state.pad
        pn = state.pad_w * state.pad_h
        self._dist = [INF] * pn

    def _reset(self, state: Builder) -> None:
        pn = state.pad_w * state.pad_h
        if len(self._dist) != pn:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray((pn + 7) // 8)
        self._q = []

    def _extract_path(
        self,
        state: Builder,
        start: Position,
        target: Position,
    ) -> list[Position]:
        cost = state.cost_grid
        pw = self._pw
        pad = self._pad
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
                if not (0 <= nx < self._w and 0 <= ny < self._h):
                    continue
                idx = ci + dy * pw + dx
                if (self._prev_visited[idx >> 3] & (1 << (idx & 7))) and cost[
                    idx
                ] < INF:
                    d = self._dist[idx]
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
        w = self._w
        pw = self._pw
        pad = self._pad
        w_bound = self._w
        h_bound = self._h
        dist = self._dist
        visited = self._visited
        q = self._q

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
            if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                return False

            ci = (current.y + pad) * pw + (current.x + pad)
            cur_dist = dist[ci]
            for dx, dy in _DIR8_DELTA:
                nx = current.x + dx
                ny = current.y + dy
                if nx < 0 or nx >= w_bound or ny < 0 or ny >= h_bound:
                    continue
                idx = ci + dy * pw + dx
                if visited[idx >> 3] & (1 << (idx & 7)):
                    continue
                move_cost = cost[idx]
                if move_cost >= INF:
                    continue
                visited[idx >> 3] |= 1 << (idx & 7)
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
            self._finished
            or self._running_target is None
            or target.distance_squared(self._running_target) > _TARGET_DRIFT_SQ
        ):
            self._reset(state)
        else:
            target = self._running_target

        self._running_target = target
        self._finished = self._run(state, ct, start, target)

        if self._finished:
            self._prev_visited = self._visited
            self._prev_target = target
            self._prev_no_path = self._no_path

        if self._prev_target is None:
            return None
        diff = target.distance_squared(self._prev_target)
        if diff <= _TARGET_DRIFT_SQ and diff < start.distance_squared(target):
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
        for pos in ct.get_nearby_tiles():
            if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
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
