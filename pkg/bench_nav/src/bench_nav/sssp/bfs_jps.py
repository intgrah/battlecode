from bench_nav.common import INF


def bfs_jps(
    n: int,
    w: int,
    pnb_dir: list[list[list[int]]],
    dir_of_offset: list[int],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    entry_dir_at = [8] * n  # start has entry_dir = 8 (no parent)
    kp = w + 1
    frontier: list[int] = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for nb in pnb_dir[node][entry_dir_at[node]]:
                if dist[nb] is INF:
                    dist[nb] = d
                    entry_dir_at[nb] = dir_of_offset[nb - node + kp]
                    next_frontier.append(nb)
        frontier = next_frontier
        d += 1
    return dist
