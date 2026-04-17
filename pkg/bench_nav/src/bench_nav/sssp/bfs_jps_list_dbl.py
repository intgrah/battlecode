from bench_nav.common import INF


def bfs_jps_list_dbl(
    n: int,
    pnb_dir: list[list[list[int]]],
    dir_of_offset: list[int],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    pnb_at: list[list[int]] = [pnb_dir[0][8]] * n
    pnb_at[start] = pnb_dir[start][8]
    a: list[int] = [start]
    b: list[int] = []
    a_append = a.append
    b_append = b.append
    d = 1
    while a:
        for node in a:
            for nb in pnb_at[node]:
                if dist[nb] is INF:
                    dist[nb] = d
                    pnb_at[nb] = pnb_dir[nb][dir_of_offset[nb - node]]
                    b_append(nb)
        a.clear()
        a, b = b, a
        a_append, b_append = b_append, a_append
        d += 1
    return dist
