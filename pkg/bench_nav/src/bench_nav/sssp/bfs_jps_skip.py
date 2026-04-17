from bench_nav.common import INF


def bfs_jps_skip(
    n: int,
    w: int,
    pnb_push_dir: list[list[list[int]]],
    pnb_set_dir: list[list[list[int]]],
    dir_of_offset: list[int],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    entry_dir_at = [8] * n
    kp = w + 1
    frontier: list[int] = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            ed = entry_dir_at[node]
            for nb in pnb_push_dir[node][ed]:
                if dist[nb] is INF:
                    dist[nb] = d
                    entry_dir_at[nb] = dir_of_offset[nb - node + kp]
                    next_frontier.append(nb)
            for nb in pnb_set_dir[node][ed]:
                if dist[nb] is INF:
                    dist[nb] = d
        frontier = next_frontier
        d += 1
    return dist
