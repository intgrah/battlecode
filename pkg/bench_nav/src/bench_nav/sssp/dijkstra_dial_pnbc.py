from __future__ import annotations

from collections import deque

from bench_nav.common import INF


def dijkstra_dial_pnbc(
    n: int, pnbc: list[list[tuple[int, int]]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    bk = [deque[int]() for _ in range(4)]
    bk[0].append(start)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        bki = bk[bi]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bki.popleft()
        if dist[node] != cur_d:
            continue
        for nb, c in pnbc[node]:
            nd = cur_d + c
            if nd < dist[nb]:
                dist[nb] = nd
                bk[nd & 3].append(nb)
    return dist
