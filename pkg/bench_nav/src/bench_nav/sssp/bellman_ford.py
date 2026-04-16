from bench_nav.common import INF


def bellman_ford(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    for _ in range(n - 1):
        changed = False
        for node in range(n):
            d = dist[node]
            if d is not INF:
                for nb in pnb[node]:
                    nd = d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        changed = True
        if not changed:
            break
    return dist
