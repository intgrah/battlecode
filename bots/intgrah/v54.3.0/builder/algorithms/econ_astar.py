from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Position

if TYPE_CHECKING:
    from builder import Builder

from util import INF

_TARGET_DRIFT_SQ = 25
_CPU_BUDGET = 1729

DIAG_WEIGHT = 4
_BRIDGE_DELTAS = [
    (dx, dy, 7)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 3 <= dx * dx + dy * dy <= 9
]
_CONV_NEIGHBORS = [
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (1, 1, DIAG_WEIGHT),
    (1, -1, DIAG_WEIGHT),
    (-1, 1, DIAG_WEIGHT),
    (-1, -1, DIAG_WEIGHT),
    *_BRIDGE_DELTAS,
]


class AStarSearch:
    def __init__(self) -> None:
        self._w = 0
        self._h = 0
        self._pw = 0
        self._ph = 0
        self._pad = 0
        self._flat_neighbors: list[tuple[int, int]] = []
        self._dist: list[int] = []
        self._visited = bytearray()
        self._prev_visited = bytearray()
        self._q: list[tuple[float, Position]] = []
        self._finished = True
        self._no_path = False
        self._prev_no_path = False
        self._running_target: Position | None = None
        self._prev_target: Position | None = None

    def _init_grid(self, state: Builder) -> None:
        self._w, self._h = state.w, state.h
        self._pw, self._ph = state.pad_w, state.pad_h
        self._pad = state.pad
        pn = self._pw * self._ph
        self._dist = [INF] * pn
        self._flat_neighbors = [
            (dy * self._pw + dx, extra) for dx, dy, extra in _CONV_NEIGHBORS
        ]
        self._visited_reset = bytes((pn + 7) // 8)

    def _reset(self, state: Builder) -> None:
        pn = state.pad_w * state.pad_h
        if len(self._dist) != pn:
            self._init_grid(state)
        self._no_path = False
        self._visited = bytearray(self._visited_reset)
        self._q = []

    def _extract_path(
        self,
        state: Builder,
        start: Position,
        target: Position,
    ) -> list[Position]:
        cost = state.conveyor_cost_grid
        pw = self._pw
        pad = self._pad
        flat_neighbors = self._flat_neighbors
        prev_visited = self._prev_visited
        dist = self._dist
        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = INF
            best = current
            ci = (current.y + pad) * pw + (current.x + pad)
            for off, extra in flat_neighbors:
                idx = ci + off
                if not (prev_visited[idx >> 3] & (1 << (idx & 7))):
                    continue
                if cost[idx] >= INF:
                    continue
                d = dist[idx] + extra
                if d < best_dist:
                    best_dist = d
                    y_p, x_p = divmod(idx, pw)
                    best = Position(x_p - pad, y_p - pad)
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
        cost = state.conveyor_cost_grid
        pw = self._pw
        pad = self._pad
        dist = self._dist
        visited = self._visited
        flat_neighbors = self._flat_neighbors
        sx_p = start.x + pad
        sy_p = start.y + pad
        gx_p = goal.x + pad
        gy_p = goal.y + pad

        gi = gy_p * pw + gx_p
        si = sy_p * pw + sx_p
        dist[gi] = 0
        visited[gi >> 3] |= 1 << (gi & 7)

        nb_count = 24
        f0 = abs(gx_p - sx_p) + abs(gy_p - sy_p)
        bk: list[list[int]] = [[] for _ in range(nb_count)]
        bk[f0 % nb_count].append(gi)
        cur_f = f0
        emp = 0

        while emp < nb_count:
            bucket = bk[cur_f % nb_count]
            if not bucket:
                cur_f += 1
                emp += 1
                continue
            emp = 0
            for node_i in bucket:
                ny_, nx_ = divmod(node_i, pw)
                node_h = abs(nx_ - sx_p) + abs(ny_ - sy_p)
                if dist[node_i] + node_h != cur_f:
                    continue
                if node_i == si:
                    return True
                if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
                    return False
                gn = dist[node_i]
                for off, extra in flat_neighbors:
                    ni = node_i + off
                    mc = cost[ni]
                    if mc >= INF:
                        continue
                    seen = visited[ni >> 3] & (1 << (ni & 7))
                    if not seen:
                        dist[ni] = INF
                    visited[ni >> 3] |= 1 << (ni & 7)
                    nd = gn + mc + extra
                    if nd >= dist[ni]:
                        continue
                    dist[ni] = nd
                    ny2, nx2 = divmod(ni, pw)
                    h_val = abs(nx2 - sx_p) + abs(ny2 - sy_p)
                    f = nd + h_val
                    bk[f % nb_count].append(ni)
            bk[cur_f % nb_count] = []
            cur_f += 1

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
        cost = state.conveyor_cost_grid
        pw = state.pad_w
        pad = state.pad
        saved: list[tuple[int, int]] = []
        for pos in state.nearby_tiles:
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

    def unreachable(self, target: Position) -> bool:
        return self.no_path and self._prev_target == target


conv_search = AStarSearch()
