from collections import deque

from bench_nav.common import INF


def bfs(n: int, pnb: list[list[int]], start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q = deque([start])
    while q:
        node = q.popleft()
        d1 = dist[node] + 1
        for nb in pnb[node]:
            if dist[nb] == INF:
                dist[nb] = d1
                q.append(nb)
    return dist
