"""Incremental multi-source shortest path (Ramalingam-Reps).

Reference: Ramalingam & Reps, 1996.

Supports batched edge mutations: call add_edge / remove_edge / update_edge
any number of times, then call propagate() once to restore the SSSP invariant.
"""

import heapq

INF = 1_000_000


class RamalingamReps[T]:
    def __init__(self) -> None:
        self.dist: dict[T, int] = {}
        self.pred: dict[T, T | None] = {}
        self.adj: dict[T, list[tuple[T, int]]] = {}
        self.inv: dict[T, list[T]] = {}
        self._heap: list[tuple[int, T]] = []

    def set_sources(self, sources: list[T]) -> None:
        for s in sources:
            self.dist[s] = 0
            self.pred[s] = s
            heapq.heappush(self._heap, (0, s))
        self.propagate()

    def should_continue(self) -> bool:
        return True

    def propagate(self) -> None:
        dist = self.dist
        pred = self.pred
        adj = self.adj
        heap = self._heap
        expanded = 0
        while heap:
            d, u = heapq.heappop(heap)
            if d != dist.get(u, INF):
                continue
            for v, cost in adj.get(u, []):
                nd = d + cost
                if nd < dist.get(v, INF):
                    dist[v] = nd
                    pred[v] = u
                    heapq.heappush(heap, (nd, v))
            expanded += 1
            if expanded & 15 == 0 and not self.should_continue():
                return

    def add_edge(self, u: T, v: T, cost: int) -> None:
        self.adj.setdefault(u, []).append((v, cost))
        self.inv.setdefault(v, []).append(u)
        du = self.dist.get(u, INF)
        if du + cost < self.dist.get(v, INF):
            heapq.heappush(self._heap, (du, u))

    def remove_edge(self, u: T, v: T) -> None:
        if u in self.adj:
            self.adj[u] = [(w, c) for w, c in self.adj[u] if w != v]
        if v in self.inv:
            self.inv[v] = [w for w in self.inv[v] if w != u]
        dv = self.dist.get(v, INF)
        if dv >= INF:
            return
        if self.pred.get(v) == u:
            self._mark_affected(v)

    def update_edge(self, u: T, v: T, old_cost: int, new_cost: int) -> None:
        edges = self.adj.get(u, [])
        found = False
        for i, (w, _c) in enumerate(edges):
            if w == v:
                edges[i] = (v, new_cost)
                found = True
                break
        if not found:
            self.add_edge(u, v, new_cost)
            return
        du = self.dist.get(u, INF)
        if new_cost < old_cost:
            if du + new_cost < self.dist.get(v, INF):
                heapq.heappush(self._heap, (du, u))
        elif new_cost > old_cost and self.pred.get(v) == u:
            self._mark_affected(v)

    def _mark_affected(self, root: T) -> None:
        stack = [root]
        affected: list[T] = []
        while stack:
            v = stack.pop()
            if self.dist.get(v, INF) >= INF:
                continue
            self.dist[v] = INF
            self.pred[v] = None
            affected.append(v)
            for w, _ in self.adj.get(v, []):
                if self.pred.get(w) == v:
                    stack.append(w)
        for v in affected:
            for u in self.inv.get(v, []):
                du = self.dist.get(u, INF)
                if du < INF:
                    heapq.heappush(self._heap, (du, u))

    def get_path(self, v: T) -> list[T] | None:
        if self.dist.get(v, INF) >= INF:
            return None
        path: list[T] = []
        visited: set[T] = set()
        current: T | None = v
        while current is not None and current != self.pred.get(current):
            if current in visited:
                return None
            visited.add(current)
            path.append(current)
            current = self.pred.get(current)
        if current is not None:
            path.append(current)
        path.reverse()
        return path
