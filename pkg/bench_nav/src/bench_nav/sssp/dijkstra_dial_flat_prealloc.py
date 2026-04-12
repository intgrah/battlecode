from bench_nav.common import INF

_BUCKETS = 900


_bk: list[int] = [0] * (256 * _BUCKETS)


def dijkstra_dial_flat_prealloc(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    bk = _bk
    ln = [0] * _BUCKETS
    bk[0] = start
    ln[0] = 1
    cur_d = 0
    max_d = 0
    while cur_d <= max_d:
        for i in range(ln[cur_d]):
            node = bk[i + (cur_d << 8)]
            if dist[node] == cur_d:
                for nb in pnb[node]:
                    nd = cur_d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bk[ln[nd] + (nd << 8)] = nb
                        ln[nd] += 1
                        if nd > max_d:  # noqa: PLR1730
                            max_d = nd
        cur_d += 1
    return dist
