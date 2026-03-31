"""D* Lite.

Incremental heuristic-guided single source shortest path (SSSP).

Reference: Koenig & Likhachev, "D* Lite", AAAI 2002.

Searches backward from goal to start. When edge costs change or the start
moves, only locally affected vertices are re-expanded.
"""

import heapq

INF = 1_000_000


class DStarLite[T]:
    def __init__(self, source: T, goal: T) -> None:
        self.done = False
        self._source = source
        self._goal = goal
        self._km = 0
        self.g: dict[T, int] = {}
        self.rhs: dict[T, int] = {}
        self._gen: dict[T, int] = {}
        self._in_queue: dict[T, bool] = {}
        self._heap: list[tuple[int, int, int, T]] = []
        self.rhs[goal] = 0
        self._insert(goal)

    def successors(self, node: T) -> list[tuple[T, int]]:
        raise NotImplementedError

    def predecessors(self, node: T) -> list[tuple[T, int]]:
        raise NotImplementedError

    def cost_heuristic(self, a: T, b: T) -> int:
        raise NotImplementedError

    def _g(self, s: T) -> int:
        return self.g.get(s, INF)

    def _rhs(self, s: T) -> int:
        return self.rhs.get(s, INF)

    def _key(self, s: T) -> tuple[int, int]:
        m = min(self._g(s), self._rhs(s))
        h = self.cost_heuristic(self._source, s)
        return (m + h + self._km, m)

    def _insert(self, s: T) -> None:
        gen = self._gen.get(s, 0) + 1
        self._gen[s] = gen
        self._in_queue[s] = True
        k = self._key(s)
        heapq.heappush(self._heap, (k[0], k[1], gen, s))

    def _remove(self, s: T) -> None:
        self._in_queue[s] = False

    def _top_key(self) -> tuple[int, int]:
        while self._heap:
            k0, k1, gen, s = self._heap[0]
            if self._in_queue.get(s, False) and self._gen.get(s, 0) == gen:
                return (k0, k1)
            heapq.heappop(self._heap)
        return (INF, INF)

    def _pop(self) -> T | None:
        while self._heap:
            _k0, _k1, gen, s = heapq.heappop(self._heap)
            if self._in_queue.get(s, False) and self._gen.get(s, 0) == gen:
                self._in_queue[s] = False
                return s
        return None

    def _update_vertex(self, u: T) -> None:
        if u != self._goal:
            best = INF
            for s, c in self.successors(u):
                val = self._g(s) + c
                best = min(best, val)
            self.rhs[u] = best
        if self._in_queue.get(u, False):
            self._remove(u)
        if self._g(u) != self._rhs(u):
            self._insert(u)

    def set_source(self, source: T) -> None:
        old = self._source
        self._source = source
        if old != source:
            self._km += self.cost_heuristic(old, source)

    def on_edge_change(self, node: T) -> None:
        self._update_vertex(node)
        for p, _ in self.predecessors(node):
            self._update_vertex(p)

    def should_continue(self) -> bool:
        return True

    def compute(self) -> None:
        expanded = 0
        while True:
            tk = self._top_key()
            sk = self._key(self._source)
            if tk >= sk and self._rhs(self._source) == self._g(self._source):
                break
            k_old = tk
            u = self._pop()
            if u is None:
                break
            k_new = self._key(u)
            if k_old < k_new:
                self._insert(u)
            elif self._g(u) > self._rhs(u):
                self.g[u] = self.rhs[u]
                for p, _ in self.predecessors(u):
                    self._update_vertex(p)
            else:
                self.g[u] = INF
                self._update_vertex(u)
                for p, _ in self.predecessors(u):
                    self._update_vertex(p)
            expanded += 1
            if expanded & 15 == 0 and not self.should_continue():
                return

    def get_path(self) -> list[T] | None:
        if self._g(self._source) >= INF:
            return None
        path = [self._source]
        s = self._source
        visited: set[T] = {s}
        while s != self._goal:
            best_next: T | None = None
            best_cost = INF
            for n, c in self.successors(s):
                val = c + self._g(n)
                if val < best_cost and n not in visited:
                    best_cost = val
                    best_next = n
            if best_next is None:
                return None
            visited.add(best_next)
            path.append(best_next)
            s = best_next
        return path

    def get_next_step(self) -> T | None:
        if self._g(self._source) >= INF:
            return None
        best_next: T | None = None
        best_cost = INF
        for n, c in self.successors(self._source):
            val = c + self._g(n)
            if val < best_cost:
                best_cost = val
                best_next = n
        return best_next
