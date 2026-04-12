from __future__ import annotations

from collections import deque

from bench_nav.common import CE, CR, INF


def dijkstra_dial_dual(
    n: int, pnb1: list[list[int]], pnb3: list[list[int]], start: int
) -> list[int]:
    """dual3 + bound append methods per distance level."""
    dist = [INF] * n
    dist[start] = 0
    bk = [deque[int]() for _ in range(4)]
    bk[0].append(start)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 0b11]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        popleft = bki.popleft
        nd1 = cur_d + CR
        bk1_append = bk[nd1 & 0b11].append
        nd3 = cur_d + CE
        bk3_append = bk[nd3 & 0b11].append
        while bki:
            node = popleft()
            if dist[node] != cur_d:
                continue
            for nb in pnb1[node]:
                if nd1 < dist[nb]:
                    dist[nb] = nd1
                    bk1_append(nb)
            for nb in pnb3[node]:
                if nd3 < dist[nb]:
                    dist[nb] = nd3
                    bk3_append(nb)
        cur_d += 1
    return dist
