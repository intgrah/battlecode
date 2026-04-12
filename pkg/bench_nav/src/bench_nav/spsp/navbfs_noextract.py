from bench_nav.common import INF, Path_


def navbfs_noextract(
    n: int,
    pnb_navbfs_push: list[list[int]],
    pnb_navbfs_set: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    pnb_push = pnb_navbfs_push
    pnb_set = pnb_navbfs_set
    dist = [INF] * n
    dist[start] = 0
    q = [start]
    append = q.append
    stop_at = INF
    for node in q:
        d = dist[node] + 1
        if node == goal:
            stop_at = d
        if d > stop_at:
            break
        for nb in pnb_push[node]:
            if d < dist[nb]:
                dist[nb] = d
                append(nb)
        for nb in pnb_set[node]:
            if d < dist[nb]:
                if nb == goal:
                    stop_at = d + 1
                dist[nb] = d
    return None
