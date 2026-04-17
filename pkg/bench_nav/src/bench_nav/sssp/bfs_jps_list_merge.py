from bench_nav.common import INF


def bfs_jps_list_merge(
    n: int,
    pnb_dir: list[list[list[int]]],
    dir_of_offset: list[int],
    start: int,
) -> list[int]:
    sentinel: list[int] = []
    pnb_at: list[list[int]] = [sentinel] * n
    pnb_at[start] = pnb_dir[start][8]
    dist = [INF] * n
    dist[start] = 0
    frontier: list[int] = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for nb in pnb_at[node]:
                if pnb_at[nb] is sentinel:
                    pnb_at[nb] = pnb_dir[nb][dir_of_offset[nb - node]]
                    next_frontier.append(nb)
        for nb in next_frontier:
            dist[nb] = d
        frontier = next_frontier
        d += 1
    return dist
