from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import CE, INF, Path_, extract_parent

if TYPE_CHECKING:
    from bench_nav.spsp.precompute_apsp import ApspTable

assert CE + 2 == 5


def astar_dial_apsp(
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
    bk = [deque[int]() for _ in range(5)]
    bk[h_start % 5].append(start)
    f = h_start
    emp = 0
    while emp < 5:
        bki = bk[f % 5]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                h_node = h_to_goal[node]
                if g[node] + h_node == f:
                    if node == goal:
                        return extract_parent(parent, start, goal)
                    g_node = g[node]
                    for nb in pnb[node]:
                        nd = g_node + cost[nb]
                        if nd < g[nb]:
                            g[nb] = nd
                            parent[nb] = node
                            bk[(nd + h_to_goal[nb]) % 5].append(nb)
        else:
            emp += 1
        f += 1
    return None
