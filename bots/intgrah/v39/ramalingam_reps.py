"""Incremental single-source shortest path (Ramalingam-Reps).

Reference: Ramalingam & Reps, 1996.

Supports batched edge mutations: call add_edge / remove_edge / update_edge
any number of times, then call propagate() once to restore the SSSP invariant.
"""

import heapq

INF = 1_000_000


class RamalingamReps:
    def __init__(self, n: int) -> None:
        self.n = n
        self.dist = [INF] * n
        self.pred = [-1] * n
        self.adj: list[list[tuple[int, int]]] = [[] for _ in range(n)]
        self.inv: list[list[int]] = [[] for _ in range(n)]
        self._heap: list[tuple[int, int]] = []

    def set_sources(self, sources: list[int]) -> None:
        for s in sources:
            self.dist[s] = 0
            self.pred[s] = s
            heapq.heappush(self._heap, (0, s))
        self.propagate()

    def propagate(self) -> None:
        dist = self.dist
        pred = self.pred
        adj = self.adj
        heap = self._heap
        while heap:
            d, u = heapq.heappop(heap)
            if d != dist[u]:
                continue
            for v, cost in adj[u]:
                nd = d + cost
                if nd < dist[v]:
                    dist[v] = nd
                    pred[v] = u
                    heapq.heappush(heap, (nd, v))

    def add_edge(self, u: int, v: int, cost: int) -> None:
        self.adj[u].append((v, cost))
        self.inv[v].append(u)
        if self.dist[u] + cost < self.dist[v]:
            heapq.heappush(self._heap, (self.dist[u], u))

    def remove_edge(self, u: int, v: int) -> None:
        self.adj[u] = [(w, c) for w, c in self.adj[u] if w != v]
        self.inv[v] = [w for w in self.inv[v] if w != u]
        if self.dist[v] >= INF:
            return
        if self.pred[v] == u:
            self._mark_affected(v)

    def update_edge(self, u: int, v: int, old_cost: int, new_cost: int) -> None:
        found = False
        for i, (w, _c) in enumerate(self.adj[u]):
            if w == v:
                self.adj[u][i] = (v, new_cost)
                found = True
                break
        if not found:
            self.add_edge(u, v, new_cost)
            return
        if new_cost < old_cost:
            if self.dist[u] + new_cost < self.dist[v]:
                heapq.heappush(self._heap, (self.dist[u], u))
        elif new_cost > old_cost and self.pred[v] == u:
            self._mark_affected(v)

    def _mark_affected(self, root: int) -> None:
        stack = [root]
        affected: list[int] = []
        while stack:
            v = stack.pop()
            if self.dist[v] >= INF:
                continue
            self.dist[v] = INF
            self.pred[v] = -1
            affected.append(v)
            for w, _ in self.adj[v]:
                if self.pred[w] == v:
                    stack.append(w)
        for v in affected:
            for u in self.inv[v]:
                if self.dist[u] < INF:
                    heapq.heappush(self._heap, (self.dist[u], u))

    def get_path(self, v: int) -> list[int] | None:
        if self.dist[v] >= INF:
            return None
        path = []
        visited: set[int] = set()
        while v != self.pred[v]:
            if v in visited:
                return None
            visited.add(v)
            path.append(v)
            v = self.pred[v]
            if v == -1:
                return None
        path.append(v)
        path.reverse()
        return path
