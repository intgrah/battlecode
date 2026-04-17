from bench_nav.common import INF


def bfs_jps_list(
    n: int,
    w: int,
    pnb_dir: list[list[list[int]]],
    dir_of_offset: list[int],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    pnb_at: list[list[int]] = [pnb_dir[0][8]] * n
    pnb_at[start] = pnb_dir[start][8]
    kp = w + 1
    frontier: list[int] = [start]
    d = 1
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            for nb in pnb_at[node]:
                if dist[nb] is INF:
                    dist[nb] = d
                    pnb_at[nb] = pnb_dir[nb][dir_of_offset[nb - node + kp]]
                    next_frontier.append(nb)
        frontier = next_frontier
        d += 1
    return dist
