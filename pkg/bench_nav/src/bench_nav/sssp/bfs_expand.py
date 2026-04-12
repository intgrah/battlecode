from __future__ import annotations

from collections import deque

from bench_nav.common import INF


def bfs_expand(n: int, cost: list[int], pnb: list[list[int]], start: int) -> list[int]:
    n2 = n + n
    dist: list[int] = [INF] * (n + n2)
    dist[start] = 0
    q: deque[int] = deque([start])
    popleft = q.popleft
    append = q.append
    while q:
        node = popleft()
        d1 = dist[node] + 1
        if node < n:
            for nb in pnb[node]:
                c = cost[nb]
                if c == 1:
                    if dist[nb] != INF:
                        continue
                    dist[nb] = d1
                    append(nb)
                else:
                    vi = nb + n2
                    if dist[vi] != INF:
                        continue
                    dist[vi] = d1
                    append(vi)
        elif node >= n2:
            nb = node - n
            if dist[nb] != INF:
                continue
            dist[nb] = d1
            append(nb)
        else:
            nb = node - n
            if dist[nb] != INF:
                continue
            dist[nb] = d1
            append(nb)
    result: list[int] = [INF] * n
    result[start] = 0
    for i in range(n):
        if dist[i] < INF:
            result[i] = dist[i]
    return result
