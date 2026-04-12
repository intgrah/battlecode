from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from bench_nav.common import INF, Path_, extract_parent

if TYPE_CHECKING:
    from bench_nav.spsp.precompute_apsp import ApspTable


def astar_heap_apsp(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    apsp: ApspTable,
    start: int,
    goal: int,
) -> Path_:
    h_to_goal = apsp.cols[goal]
    g = [INF] * n
    g[start] = 0
    parent = [-1] * n
    parent[start] = start
    h_start = h_to_goal[start]
    q = [(h_start, h_start, start)]
    while q:
        f, h_node, node = heapq.heappop(q)
        if f > g[node] + h_node:
            continue
        if node == goal:
            return extract_parent(parent, start, goal)
        g_node = g[node]
        for nb in pnb[node]:
            nd = g_node + cost[nb]
            if nd < g[nb]:
                g[nb] = nd
                parent[nb] = node
                h_nb = h_to_goal[nb]
                heapq.heappush(q, (nd + h_nb, h_nb, nb))
    return None
