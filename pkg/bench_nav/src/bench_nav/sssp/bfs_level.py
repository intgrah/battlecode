from bench_nav.common import INF


def bfs_level(n: int, pnb: list[list[int]], start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    frontier = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        append = next_frontier.append
        for node in frontier:
            for nb in pnb[node]:
                if dist[nb] is INF:
                    dist[nb] = d
                    append(nb)
        frontier = next_frontier
        d += 1
    return dist
