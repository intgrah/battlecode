from __future__ import annotations

from typing import override

from bench_nav.common import CE, INF, Path_, bfs_dist, extract_parent
from bench_nav.spsp.astar._base import AstarBase
from bench_nav.types import PrecompCtx

assert CE + 2 == 5


class AstarDialPrecompLifo(AstarBase):
    """LIFO within bucket variant of astar_dial_precomp. BFS-from-start heuristic cached per source."""

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        super().__init__(ctx)
        self._h_cache: dict[int, list[int]] = {}

    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        h = self._h_cache.get(start)
        if h is None:
            h = bfs_dist(self.n, pnb, start)
            self._h_cache[start] = h
        g = [INF] * self.n
        g[goal] = 0
        parent = [-1] * self.n
        parent[goal] = goal
        h_goal = h[goal]
        if h_goal >= INF:
            return None
        bk: list[list[int]] = [[] for _ in range(5)]
        bk[h_goal % 5].append(goal)
        f = h_goal
        emp = 0
        while emp < 5:
            bki = bk[f % 5]
            if bki:
                emp = 0
                while bki:
                    node = bki.pop()
                    g_node = g[node]
                    if g_node + h[node] != f:
                        continue
                    if node == start:
                        path = extract_parent(parent, goal, start)
                        if path is not None:
                            path.reverse()
                        return path
                    for nb in pnb[node]:
                        nd = g_node + cost[nb]
                        if nd < g[nb]:
                            g[nb] = nd
                            parent[nb] = node
                            bk[(nd + h[nb]) % 5].append(nb)
            else:
                emp += 1
            f += 1
        return None
