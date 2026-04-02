"""A*.

Heuristic-guided single source shortest path (SSSP).
"""

import heapq

INF = 1_000_000


class Astar[T]:
    def __init__(self, source: T, goals: set[T]) -> None:
        self.done = False
        self._result: list[T] | None = None
        self.goals = goals

        if source in goals:
            self.done = True
            self._result = [source]
            return

        self.g: dict[T, int] = {source: 0}
        self.parent: dict[T, T | None] = {source: None}
        self._best_h = INF
        self._best_node = source
        h0 = self.heuristic(source)
        self.heap: list[tuple[int, int, T]] = [(h0, 0, source)]

    def get_neighbors(self, node: T) -> list[tuple[T, int]]:
        raise NotImplementedError

    def heuristic(self, node: T) -> int:
        raise NotImplementedError

    def should_continue(self) -> bool:
        return True

    def _extract_path(self, node: T) -> list[T]:
        path: list[T] = []
        current: T | None = node
        while current is not None:
            path.append(current)
            current = self.parent.get(current)
        path.reverse()
        return path

    def compute(self) -> None:
        if self.done:
            return

        g = self.g
        parent = self.parent
        heap = self.heap
        goals = self.goals
        heuristic = self.heuristic
        get_neighbors = self.get_neighbors
        should_continue = self.should_continue

        expanded = 0
        while heap:
            f_val, _, node = heapq.heappop(heap)

            if f_val > g.get(node, INF) + heuristic(node):
                continue

            if node in goals:
                self._result = self._extract_path(node)
                self.done = True
                return

            expanded += 1
            if expanded & 15 == 0 and not should_continue():
                return

            g_node = g[node]
            for neighbor, cost in get_neighbors(node):
                nd = g_node + cost
                if nd >= g.get(neighbor, INF):
                    continue
                g[neighbor] = nd
                parent[neighbor] = node
                hval = heuristic(neighbor)
                heapq.heappush(heap, (nd + hval, hval, neighbor))
                if hval < self._best_h:
                    self._best_h = hval
                    self._best_node = neighbor

        if not heap:
            self.done = True

    def get_path(self) -> list[T] | None:
        if self._result is not None:
            return self._result
        if self._best_h < INF:
            return self._extract_path(self._best_node)
        return None
