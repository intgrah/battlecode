from bench_nav.common import INF


def bfs_jps_list_off(
    n: int,
    pnb_by_offset: list[list[list[int]]],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    pnb_at: list[list[int]] = [pnb_by_offset[0][0]] * n
    pnb_at[start] = pnb_by_offset[start][0]
    frontier: list[int] = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for nb in pnb_at[node]:
                if dist[nb] is INF:
                    dist[nb] = d
                    pnb_at[nb] = pnb_by_offset[nb][nb - node]
                    next_frontier.append(nb)
        frontier = next_frontier
        d += 1
    return dist
