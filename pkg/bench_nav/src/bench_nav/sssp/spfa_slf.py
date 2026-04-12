from collections import deque

from bench_nav.common import CR, INF

assert CR == 1


def spfa_slf(n: int, cost: list[int], pnb: list[list[int]], start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q: deque[int] = deque([start])
    while q:
        node = q.popleft()
        d = dist[node]
        for nb in pnb[node]:
            nd = d + cost[nb]
            if nd < dist[nb]:
                dist[nb] = nd
                if cost[nb] == 1:
                    q.appendleft(nb)
                else:
                    q.append(nb)
    return dist
