from collections import deque

from bench_nav.common import CR, INF

assert CR == 1


def spfa_slf(n: int, cost: list[int], pnb: list[list[int]], start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q = deque([start])
    popleft = q.popleft
    appendleft = q.appendleft
    append = q.append
    while q:
        node = popleft()
        d = dist[node]
        for nb in pnb[node]:
            nd = d + cost[nb]
            if nd < dist[nb]:
                dist[nb] = nd
                if cost[nb] == 1:
                    appendleft(nb)
                else:
                    append(nb)
    return dist
