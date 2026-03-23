import heapq

from cambc import Controller

INF = 1_000_000


class Astar:
    def __init__(self, w: int, h: int, sx: int, sy: int) -> None:
        self.w = w
        self.h = h
        self.done = False
        self._result: list[tuple[int, int]] | None = None

        si = sy * w + sx
        if self.is_goal(sx, sy):
            self.done = True
            self._result = [(sx, sy)]
            return

        n = w * h
        self.g = [INF] * n
        self.g[si] = 0
        self.parent = [-1] * n
        self._best_h = INF
        self._best_ni = si
        self.heap: list[tuple[int, int, int]] = [(0, 0, si)]

    def is_goal(self, x: int, y: int) -> bool:
        raise NotImplementedError

    def get_neighbors(self, cx: int, cy: int) -> list[tuple[int, int, int]]:
        raise NotImplementedError

    def heuristic(self, x: int, y: int) -> int:
        raise NotImplementedError

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
        h = self.h
        g = self.g
        parent = self.parent
        heap = self.heap
        is_goal = self.is_goal
        get_neighbors = self.get_neighbors
        heuristic = self.heuristic

        expanded = 0
        while heap:
            f_val, _, ci = heapq.heappop(heap)
            cx = ci % w
            cy = ci // w

            if f_val > g[ci] + heuristic(cx, cy):
                continue

            if is_goal(cx, cy):
                self._result = self._extract_path(ci)
                self.done = True
                return

            expanded += 1
            if expanded & 15 == 0 and ct.get_cpu_time_elapsed() >= budget_us:
                return

            for nx, ny, cost in get_neighbors(cx, cy):
                if nx < 0 or nx >= w or ny < 0 or ny >= h:
                    continue
                ni = ny * w + nx
                nd = g[ci] + cost
                if nd >= g[ni]:
                    continue
                g[ni] = nd
                parent[ni] = ci
                hval = heuristic(nx, ny)
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
