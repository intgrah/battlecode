from typing import Final

from bench_nav.common import INF

MAX_D: Final = 300


def bfs_buckets(n: int, pnb: list[list[int]], start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    buckets: list[list[int]] = [[] for _ in range(MAX_D)]
    buckets[0].append(start)
    d = 1
    for frontier in buckets:
        if not frontier:
            break
        append = buckets[d].append
        for node in frontier:
            for nb in pnb[node]:
                if dist[nb] is INF:
                    dist[nb] = d
                    append(nb)
        d += 1
    return dist
