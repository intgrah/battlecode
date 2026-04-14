from bench_nav.common import CE, INF, Path_

assert CE == 3


def bfs_dist(n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
    dist = [INF] * n
    dist[start] = 0
    q = [start]
    append = q.append
    for node in q:
        d = dist[node] + 1
        for nb in pnb[node]:
            if d < dist[nb]:
                dist[nb] = d
                append(nb)
    if dist[goal] >= INF:
        return None
    path = [goal]
    cur = goal
    while cur != start:
        d = dist[cur] - 1
        for nb in pnb[cur]:
            if dist[nb] == d:
                path.append(nb)
                cur = nb
                break
        else:
            return None
    path.reverse()
    return path
