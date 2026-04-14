import heapq

from bench_nav.common import INF


def dijkstra_heap(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q = [(0, start)]
    while q:
        d, node = heapq.heappop(q)
        if d > dist[node]:
            continue
        for nb in pnb[node]:
            nd = d + cost[nb]
            if nd < dist[nb]:
                dist[nb] = nd
                heapq.heappush(q, (nd, nb))
    return dist
