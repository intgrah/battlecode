from __future__ import annotations

from collections import deque

from bench_nav.common import CE, CR, INF

assert CR == 1
assert CE == 3


class ApspTable:
    __slots__ = ("cols",)

    def __init__(self, cols: list[list[int]]) -> None:
        self.cols = cols


def precompute_apsp(n: int, cost: list[int], pnb: list[list[int]]) -> ApspTable:
    rows: list[list[int]] = []
    for start in range(n):
        if cost[start] >= INF:
            rows.append([INF] * n)
            continue
        dist: list[int] = [INF] * n
        dist[start] = 0
        bk: list[deque[int]] = [deque() for _ in range(4)]
        bk[0].append(start)
        cur_d = 0
        gap = 0
        while gap < 4:
            bki = bk[cur_d & 3]
            if not bki:
                cur_d += 1
                gap += 1
                continue
            gap = 0
            node = bki.popleft()
            if dist[node] != cur_d:
                continue
            for nb in pnb[node]:
                nd = cur_d + cost[nb]
                if nd < dist[nb]:
                    dist[nb] = nd
                    bk[nd & 3].append(nb)
        rows.append(dist)
    cols = [[rows[i][j] for i in range(n)] for j in range(n)]
    return ApspTable(cols)
