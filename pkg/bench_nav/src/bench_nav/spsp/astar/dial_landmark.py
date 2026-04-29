from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, override

from bench_nav.common import CE, INF, Path_, bfs_dist, extract_parent
from bench_nav.spsp.astar._base import AstarBase

if TYPE_CHECKING:
    from bench_nav.types import PrecompCtx

assert CE + 2 == 5

_K_LANDMARKS = 4


class AstarDialLandmark(AstarBase):
    """Backward A* (Dial's) with ALT landmark heuristic.

    Selects _K_LANDMARKS landmarks via farthest-point on the passable set in __init__
    and precomputes BFS dist from each landmark. Per query, heuristic is
    max over landmarks of |dist(landmark, v) - dist(landmark, start)|.
    """

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        super().__init__(ctx)
        passable = [i for i in range(ctx.n) if self.cost[i] < INF]
        landmark_dists: list[list[int]] = []
        if passable:
            landmark_dists.append(bfs_dist(ctx.n, self.pnb, passable[0]))
            for _ in range(_K_LANDMARKS - 1):
                best = -1
                best_min_d = -1
                for tile in passable:
                    min_d = min(ld[tile] for ld in landmark_dists)
                    if min_d > best_min_d:
                        best_min_d = min_d
                        best = tile
                landmark_dists.append(bfs_dist(ctx.n, self.pnb, best))
        self.landmark_dists = landmark_dists

    @override
    def plan(self, start: int, goal: int) -> Path_:
        cost = self.cost
        pnb = self.pnb
        landmark_dists = self.landmark_dists
        k = len(landmark_dists)
        start_ld = [landmark_dists[j][start] for j in range(k)]
        g = [INF] * self.n
        g[goal] = 0
        parent = [-1] * self.n
        parent[goal] = goal
        h_goal = max(abs(landmark_dists[j][goal] - start_ld[j]) for j in range(k))
        bk: list[deque[int]] = [deque() for _ in range(5)]
        bk[h_goal % 5].append(goal)
        f = h_goal
        emp = 0
        while emp < 5:
            bki = bk[f % 5]
            if bki:
                emp = 0
                popleft = bki.popleft
                while bki:
                    node = popleft()
                    g_node = g[node]
                    h_node = max(
                        abs(landmark_dists[j][node] - start_ld[j]) for j in range(k)
                    )
                    if g_node + h_node != f:
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
                            h_nb = max(
                                abs(landmark_dists[j][nb] - start_ld[j])
                                for j in range(k)
                            )
                            bk[(nd + h_nb) % 5].append(nb)
            else:
                emp += 1
            f += 1
        return None
