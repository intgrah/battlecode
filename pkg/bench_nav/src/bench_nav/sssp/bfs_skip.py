from bench_nav.common import INF


def bfs_skip(
    n: int,
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q = [start]
    append = q.append
    for node in q:
        d = dist[node] + 1
        for nb in pnb_push[node]:
            if dist[nb] is INF:
                dist[nb] = d
                append(nb)
        for nb in pnb_set[node]:
            if dist[nb] is INF:
                dist[nb] = d
    return dist
