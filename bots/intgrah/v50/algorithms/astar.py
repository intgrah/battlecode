import heapq
from collections.abc import Callable

INF = 1_000_000


class Astar[T]:
    def __init__(self, source: T, goals: set[T]) -> None:
        self._done = False
        self._result: list[T] | None = None
        self._goals = goals

        if source in goals:
            self._done = True
            self._result = [source]
            return

        self._g: dict[T, int] = {source: 0}
        self._parent: dict[T, T | None] = {source: None}
        self._best_h = INF
        self._best_node = source
        h0 = self.heuristic(source)
        self._heap: list[tuple[int, int, T]] = [(h0, 0, source)]

    def get_neighbors(self, node: T) -> list[tuple[T, int]]: ...
    def heuristic(self, node: T) -> int: ...

    def _extract_path(self, node: T) -> list[T]:
        path: list[T] = []
        current: T | None = node
        while current is not None:
            path.append(current)
            current = self._parent.get(current)
        path.reverse()
        return path

    def compute(
        self,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> list[T] | None:
        if self._done:
            return self._result

        g = self._g
        parent = self._parent
        heap = self._heap
        goals = self._goals

        expanded = 0
        while heap:
            f_val, _, node = heapq.heappop(heap)

            if f_val > g.get(node, INF) + self.heuristic(node):
                continue

            if node in goals:
                self._result = self._extract_path(node)
                self._done = True
                return self._result

            expanded += 1
            if expanded & 15 == 0 and not within_budget():
                break

            g_node = g[node]
            for neighbor, cost in self.get_neighbors(node):
                nd = g_node + cost
                if nd >= g.get(neighbor, INF):
                    continue
                g[neighbor] = nd
                parent[neighbor] = node
                hval = self.heuristic(neighbor)
                heapq.heappush(heap, (nd + hval, hval, neighbor))
                if hval < self._best_h:
                    self._best_h = hval
                    self._best_node = neighbor

        if not heap:
            self._done = True

        if self._result is not None:
            return self._result
        if self._best_h < INF:
            return self._extract_path(self._best_node)
        return None

    @property
    def exhausted(self) -> bool:
        return self._done
