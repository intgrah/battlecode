from collections import deque

from bench_nav.common import INF


def bfs_expand(n: int, cost: list[int], pnb: list[list[int]], start: int) -> list[int]:
    n2 = n + n
    dist = [INF] * (n + n2)
    dist[start] = 0
    q = deque([start])
    popleft = q.popleft
    append = q.append
    while q:
        node = popleft()
        d1 = dist[node] + 1
        if node < n:
            for nb in pnb[node]:
                c = cost[nb]
                if c == 1:
                    if dist[nb] is INF:
                        dist[nb] = d1
                        append(nb)
                else:
                    vi = nb + n2
                    if dist[vi] is INF:
                        dist[vi] = d1
                        append(vi)
        elif node >= n2:
            nb = node - n
            if dist[nb] is INF:
                dist[nb] = d1
                append(nb)
        else:
            nb = node - n
            if dist[nb] is INF:
                dist[nb] = d1
                append(nb)
    result = [INF] * n
    result[start] = 0
    for i in range(n):
        if dist[i] is not INF:
            result[i] = dist[i]
    return result
