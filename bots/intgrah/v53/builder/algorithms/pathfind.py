from __future__ import annotations

import heapq
import random
from typing import TYPE_CHECKING

from cambc import Controller, Position
from util import DIR8_DELTA

if TYPE_CHECKING:
    from array import array
    from collections.abc import Callable

    from builder.state import State

_INF = float("inf")
_TARGET_DRIFT_SQ = 25
_CPU_BUDGET = 1729
_TIEBREAK_EPS = 1e-5

_DIR8_DELTA = DIR8_DELTA.copy()
random.shuffle(_DIR8_DELTA)


class AStarSearch:
    def __init__(
        self,
        neighbors: list[tuple[int, int, int]],
        heuristic: Callable[[Position, Position], float],
        cost_grid_attr: str,
        *,
        allow_relaxation: bool = False,
    ) -> None:
        self._neighbors = neighbors
        self._heuristic = heuristic
        self._cost_attr = cost_grid_attr
        self._relax = allow_relaxation

        self._w = 0
        self._h = 0
        self._dist: list[float] = []
        self._visited = bytearray()
        self._prev_visited = bytearray()
        self._q: list[tuple[float, Position]] = []
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _init_grid(self, state: State) -> None:
        self._w, self._h = state.w, state.h
        self._dist = [_INF] * (self._w * self._h)

    def _reset(self, state: State) -> None:
        n = state.w * state.h
        if len(self._dist) != n:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray((n + 7) // 8)
        self._q = []

    def _cost_grid(self, state: State) -> array[float]:
        return getattr(state, self._cost_attr)

    def _extract_path(
        self, state: State, start: Position, target: Position
    ) -> list[Position]:
        cost = self._cost_grid(state)
        w = self._w
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = _INF
            best = current
            for dx, dy, extra in self._neighbors:
                nx, ny = current.x + dx, current.y + dy
                idx = ny * w + nx
                if (
                    0 <= nx < self._w
                    and 0 <= ny < self._h
                    and (self._prev_visited[idx // 8] & (1 << (idx % 8)))
                    and cost[idx] != _INF
                ):
                    d = self._dist[idx] + extra
                    if d < best_dist:
                        best_dist = d
                        best = Position(nx, ny)
            current = best
        path.append(target)
        return path

    def _run(
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> bool:
        cost = self._cost_grid(state)
        w = self._w
        h = self._heuristic
        dist = self._dist
        visited = self._visited
        q = self._q
        relax = self._relax

        idx = goal.y * w + goal.x
        dist[idx] = 0
        visited[idx // 8] |= 1 << (idx % 8)
        heapq.heappush(q, (0, goal))

        while q:
            _, current = heapq.heappop(q)
            if current == start:
                return True
            if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                return False

            cur_dist = dist[current.y * w + current.x]
            for dx, dy, extra in self._neighbors:
                nx, ny = current.x + dx, current.y + dy
                if not (0 <= nx < self._w and 0 <= ny < self._h):
                    continue
                idx = ny * w + nx
                seen = visited[idx // 8] & (1 << (idx % 8))
                if relax and not seen:
                    dist[idx] = _INF
                if not relax and seen:
                    continue
                visited[idx // 8] |= 1 << (idx % 8)
                move_cost = cost[idx]
                if move_cost == _INF:
                    continue
                new_dist = cur_dist + move_cost + extra
                if relax and new_dist >= dist[idx]:
                    continue
                dist[idx] = new_dist
                nb = Position(nx, ny)
                heapq.heappush(q, (new_dist + h(nb, start), nb))

        self._no_path = True
        return True

    def search(
        self, state: State, ct: Controller, start: Position, target: Position
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
        self, state: State, ct: Controller, start: Position, goal: Position
    ) -> list[Position] | None:
        cost = self._cost_grid(state)
        saved: list[tuple[int, float]] = []
        for pos in ct.get_nearby_tiles(2):
            if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
                idx = pos.y * state.w + pos.x
                saved.append((idx, cost[idx]))
                cost[idx] = _INF
        result = self.search(state, ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result

    @property
    def no_path(self) -> bool:
        return self._prev_no_path


def _chebyshev(a: Position, b: Position) -> float:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return max(dx, dy) + _TIEBREAK_EPS * (dx + dy)


def _manhattan(a: Position, b: Position) -> float:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return (dx + dy) + _TIEBREAK_EPS * (dx + dy)


DIAG_WEIGHT = 4

_MOVE_NEIGHBORS = [(dx, dy, 0) for dx, dy in _DIR8_DELTA]
_CONV_NEIGHBORS = [
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (1, 1, DIAG_WEIGHT),
    (1, -1, DIAG_WEIGHT),
    (-1, 1, DIAG_WEIGHT),
    (-1, -1, DIAG_WEIGHT),
]
random.shuffle(_CONV_NEIGHBORS)

move_search = AStarSearch(_MOVE_NEIGHBORS, _chebyshev, "cost_grid")
conv_search = AStarSearch(
    _CONV_NEIGHBORS, _manhattan, "conveyor_cost_grid", allow_relaxation=True
)


def pathfind(
    state: State, ct: Controller, start: Position, target: Position
) -> list[Position] | None:
    return move_search.search(state, ct, start, target)


def pathfind_blocked(
    state: State, ct: Controller, start: Position, goal: Position
) -> list[Position] | None:
    return move_search.search_blocked(state, ct, start, goal)


def conv_pathfind(
    state: State, ct: Controller, start: Position, target: Position
) -> list[Position] | None:
    return conv_search.search(state, ct, start, target)


def conv_pathfind_blocked(
    state: State, ct: Controller, start: Position, goal: Position
) -> list[Position] | None:
    return conv_search.search_blocked(state, ct, start, goal)


def conv_unreachable(target: Position) -> bool:
    return conv_search.no_path and conv_search._prev_target == target
