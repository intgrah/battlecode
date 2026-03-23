import heapq

from cambc import Controller

INF = 1_000_000


class Astar:
    def __init__(
        self,
        w: int,
        h: int,
        sx: int,
        sy: int,
        goals: set[int],
        edges: list[list[tuple[int, int, int]]],
        h_table: list[int],
    ) -> None:
        self.w = w
        self.h = h
        self.done = False
        self._result: list[tuple[int, int]] | None = None

        si = sy * w + sx
        if si in goals:
            self.done = True
            self._result = [(sx, sy)]
            return

        n = w * h
        self.g = [INF] * n
        self.g[si] = 0
        self.parent = [-1] * n
        self._best_h = INF
        self._best_ni = si
        self.heap: list[tuple[int, int, int]] = [(h_table[si], 0, si)]
        self.goals = goals
        self.edges = edges
        self.h_table = h_table

    def _extract_path(self, ni: int) -> list[tuple[int, int]]:
        w = self.w
        path: list[tuple[int, int]] = []
        while ni != -1:
            path.append((ni % w, ni // w))
            ni = self.parent[ni]
        path.reverse()
        return path

    def compute(self, ct: Controller, budget_us: int) -> None:
        if self.done:
            return

        w = self.w
        g = self.g
        parent = self.parent
        heap = self.heap
        goals = self.goals
        edges = self.edges
        h_table = self.h_table

        expanded = 0
        while heap:
            f_val, _, ci = heapq.heappop(heap)

            if f_val > g[ci] + h_table[ci]:
                continue

            if ci in goals:
                self._result = self._extract_path(ci)
                self.done = True
                return

            expanded += 1
            if expanded & 15 == 0 and ct.get_cpu_time_elapsed() >= budget_us:
                return

            for ni, cost in edges[ci]:
                nd = g[ci] + cost
                if nd >= g[ni]:
                    continue
                g[ni] = nd
                parent[ni] = ci
                hval = h_table[ni]
                heapq.heappush(heap, (nd + hval, hval, ni))
                if hval < self._best_h:
                    self._best_h = hval
                    self._best_ni = ni

        if not heap:
            self.done = True

    def get_path(self) -> list[tuple[int, int]] | None:
        if self._result is not None:
            return self._result
        if self._best_h < INF:
            return self._extract_path(self._best_ni)
        return None
