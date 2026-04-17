from bench_nav.common import INF


def bfs_skip_level(
    n: int,
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    start: int,
) -> list[int]:
    inf = INF
    dist = [inf] * n
    dist[start] = 0
    frontier = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for nb in pnb_push[node]:
                if dist[nb] is inf:
                    dist[nb] = d
                    next_frontier.append(nb)
            for nb in pnb_set[node]:
                if dist[nb] is inf:
                    dist[nb] = d
        frontier = next_frontier
        d += 1
    return dist
