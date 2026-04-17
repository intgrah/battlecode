from bench_nav.common import INF


def bfs_jps_list_defer(
    n: int,
    pnb_by_offset: list[list[list[int]]],
    start: int,
) -> list[int]:
    sentinel: list[int] = []
    pnb_at = [sentinel] * n
    pnb_at[start] = pnb_by_offset[start][0]
    frontier = [start]
    levels = [frontier]
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for nb in pnb_at[node]:
                if pnb_at[nb] is sentinel:
                    pnb_at[nb] = pnb_by_offset[nb][nb - node]
                    next_frontier.append(nb)
        levels.append(next_frontier)
        frontier = next_frontier
    dist = [INF] * n
    for d, level in enumerate(levels):
        for nb in level:
            dist[nb] = d
    return dist
