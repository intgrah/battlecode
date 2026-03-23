"""D* Lite incremental pathfinding.

Reference: Koenig & Likhachev, "D* Lite", AAAI 2002.

Searches backward from goal to start. When edge costs change or the start
moves, only locally affected vertices are re-expanded.
"""

import heapq
from collections.abc import Callable

INF = 1_000_000

Neighbors = Callable[[int, int], list[tuple[int, int, int]]]
Heuristic = Callable[[int, int, int, int], int]


class DStarLite:
    def __init__(
        self,
        w: int,
        h: int,
        successors: Neighbors,
        predecessors: Neighbors,
        heuristic: Heuristic,
    ) -> None:
        self.w = w
        self.h = h
        self.successors = successors
        self.predecessors = predecessors
        self.heuristic = heuristic
        n = w * h
        self.g = [INF] * n
        self.rhs = [INF] * n
        self._gen = [0] * n
        self._in_queue = [False] * n
        self._heap: list[tuple[int, int, int, int]] = []
        self._km = 0
        self._start = -1
        self._goal = -1
        self._initialized = False

    def _idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def _xy(self, i: int) -> tuple[int, int]:
        return i % self.w, i // self.w

    def _key(self, s: int) -> tuple[int, int]:
        m = min(self.g[s], self.rhs[s])
        sx, sy = self._xy(s)
        stx, sty = self._xy(self._start)
        h = self.heuristic(stx, sty, sx, sy)
        return (m + h + self._km, m)

    def _insert(self, s: int) -> None:
        self._gen[s] += 1
        self._in_queue[s] = True
        k = self._key(s)
        heapq.heappush(self._heap, (k[0], k[1], self._gen[s], s))

    def _remove(self, s: int) -> None:
        self._in_queue[s] = False

    def _top_key(self) -> tuple[int, int]:
        while self._heap:
            k0, k1, gen, s = self._heap[0]
            if self._in_queue[s] and self._gen[s] == gen:
                return (k0, k1)
            heapq.heappop(self._heap)
        return (INF, INF)

    def _pop(self) -> int | None:
        while self._heap:
            _k0, _k1, gen, s = heapq.heappop(self._heap)
            if self._in_queue[s] and self._gen[s] == gen:
                self._in_queue[s] = False
                return s
        return None

    def _update_vertex(self, u: int) -> None:
        if u != self._goal:
            ux, uy = self._xy(u)
            best = INF
            for sx, sy, c in self.successors(ux, uy):
                si = self._idx(sx, sy)
                val = self.g[si] + c
                best = min(best, val)
            self.rhs[u] = best
        if self._in_queue[u]:
            self._remove(u)
        if self.g[u] != self.rhs[u]:
            self._insert(u)

    def initialize(self, start: tuple[int, int], goal: tuple[int, int]) -> None:
        n = self.w * self.h
        self.g = [INF] * n
        self.rhs = [INF] * n
        self._gen = [0] * n
        self._in_queue = [False] * n
        self._heap = []
        self._km = 0
        self._start = self._idx(start[0], start[1])
        self._goal = self._idx(goal[0], goal[1])
        self.rhs[self._goal] = 0
        self._insert(self._goal)
        self._initialized = True

    def set_start(self, start: tuple[int, int]) -> None:
        old_start = self._start
        self._start = self._idx(start[0], start[1])
        if old_start != self._start:
            old_x, old_y = self._xy(old_start)
            new_x, new_y = self._xy(self._start)
            self._km += self.heuristic(old_x, old_y, new_x, new_y)

    def on_edge_change(self, x: int, y: int) -> None:
        if not self._initialized:
            return
        i = self._idx(x, y)
        self._update_vertex(i)
        for px, py, _ in self.predecessors(x, y):
            self._update_vertex(self._idx(px, py))

    def compute(self, budget: int = 500) -> None:
        if not self._initialized:
            return
        expanded = 0
        while expanded < budget:
            tk = self._top_key()
            sk = self._key(self._start)
            if tk >= sk and self.rhs[self._start] == self.g[self._start]:
                break
            k_old = tk
            u = self._pop()
            if u is None:
                break
            k_new = self._key(u)
            if k_old < k_new:
                self._insert(u)
            elif self.g[u] > self.rhs[u]:
                self.g[u] = self.rhs[u]
                ux, uy = self._xy(u)
                for px, py, _ in self.predecessors(ux, uy):
                    self._update_vertex(self._idx(px, py))
            else:
                self.g[u] = INF
                ux, uy = self._xy(u)
                self._update_vertex(u)
                for px, py, _ in self.predecessors(ux, uy):
                    self._update_vertex(self._idx(px, py))
            expanded += 1

    def get_path(self) -> list[tuple[int, int]] | None:
        if not self._initialized or self.g[self._start] >= INF:
            return None
        path = [self._xy(self._start)]
        s = self._start
        visited: set[int] = {s}
        while s != self._goal:
            sx, sy = self._xy(s)
            best_next = -1
            best_cost = INF
            for nx, ny, c in self.successors(sx, sy):
                ni = self._idx(nx, ny)
                val = c + self.g[ni]
                if val < best_cost and ni not in visited:
                    best_cost = val
                    best_next = ni
            if best_next == -1:
                return None
            visited.add(best_next)
            path.append(self._xy(best_next))
            s = best_next
        return path

    def get_next_step(self) -> tuple[int, int] | None:
        if not self._initialized or self.g[self._start] >= INF:
            return None
        sx, sy = self._xy(self._start)
        best_next: tuple[int, int] | None = None
        best_cost = INF
        for nx, ny, c in self.successors(sx, sy):
            ni = self._idx(nx, ny)
            val = c + self.g[ni]
            if val < best_cost:
                best_cost = val
                best_next = (nx, ny)
        return best_next
