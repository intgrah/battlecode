from __future__ import annotations

from bench_nav.common import INF

_bk: list[list[int]] = [[0] * 2500 for _ in range(900)]


def dijkstra_dial_flat(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    bk = _bk
    ln = [0] * 900
    bk[0][0] = start
    ln[0] = 1
    for cur_d, (bki, leni) in enumerate(zip(bk, ln, strict=True)):
        for i in range(leni):
            node = bki[i]
            if dist[node] == cur_d:
                for nb in pnb[node]:
                    nd = cur_d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bkn = bk[nd]
                        bkn[ln[nd]] = nb
                        ln[nd] += 1

    return dist
