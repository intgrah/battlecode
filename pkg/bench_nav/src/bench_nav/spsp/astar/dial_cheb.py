from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CE, CR, INF, Path_, extract_parent
from bench_nav.spsp.astar._base import AstarBase

assert CE + 2 == 5
assert CR == 1


def _astar_dial_cheb(
    w: int, n: int, cost: list[int], pnb: list[list[int]], start: int, goal: int
) -> Path_:
    start_x, start_y = start % w, start // w
    goal_x, goal_y = goal % w, goal // w
    g = [INF] * n
    g[start] = 0
    parent = [-1] * n
    parent[start] = start
    h_start = max(abs(start_x - goal_x), abs(start_y - goal_y))
    bk: list[deque[int]] = [deque() for _ in range(5)]
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
                g_node = g[node]
                if g_node + max(abs(node % w - goal_x), abs(node // w - goal_y)) != f:
                    continue
                if node == goal:
                    return extract_parent(parent, start, goal)
                for nb in pnb[node]:
                    nd = g_node + cost[nb]
                    if nd < g[nb]:
                        g[nb] = nd
                        parent[nb] = node
                        h_nb = max(abs(nb % w - goal_x), abs(nb // w - goal_y))
                        bk[(nd + h_nb) % 5].append(nb)
        else:
            emp += 1
        f += 1
    return None


class AstarDialChebSpsp(AstarBase):
    @override
    def plan(self, start: int, goal: int) -> Path_:
        return _astar_dial_cheb(self.w, self.n, self.cost, self.pnb, start, goal)
