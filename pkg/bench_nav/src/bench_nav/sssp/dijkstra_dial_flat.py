from bench_nav.common import INF

_BUCKETS = 900


def dijkstra_dial_flat(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    bk: list[list[int]] = [[] for _ in range(_BUCKETS)]
    bk[0].append(start)
    cur_d = 0
    max_d = 0
    while cur_d <= max_d:
        for node in bk[cur_d]:
            if dist[node] is cur_d:
                for nb in pnb[node]:
                    nd = cur_d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bk[nd].append(nb)
                        if nd > max_d:  # noqa: PLR1730
                            max_d = nd
        cur_d += 1
    return dist
