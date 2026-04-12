from collections import deque

from bench_nav.common import INF, Path_, extract_parent


def bibfs(n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
    parent_f: list[int] = [-1] * n
    parent_b: list[int] = [-1] * n
    dist_f: list[int] = [INF] * n
    dist_b: list[int] = [INF] * n
    parent_f[start] = start
    parent_b[goal] = goal
    dist_f[start] = 0
    dist_b[goal] = 0
    qf: deque[int] = deque([start])
    qb: deque[int] = deque([goal])
    best = INF
    meet = -1
    while qf or qb:
        min_remaining = 0
        if qf:
            min_remaining += dist_f[qf[0]]
        if qb:
            min_remaining += dist_b[qb[0]]
        if min_remaining >= best:
            break
        if qf and (not qb or len(qf) <= len(qb)):
            node = qf.popleft()
            d = dist_f[node] + 1
            for nb in pnb[node]:
                if dist_f[nb] <= d:
                    continue
                dist_f[nb] = d
                parent_f[nb] = node
                qf.append(nb)
                if dist_b[nb] < INF and d + dist_b[nb] < best:
                    best = d + dist_b[nb]
                    meet = nb
        elif qb:
            node = qb.popleft()
            d = dist_b[node] + 1
            for nb in pnb[node]:
                if dist_b[nb] <= d:
                    continue
                dist_b[nb] = d
                parent_b[nb] = node
                qb.append(nb)
                if dist_f[nb] < INF and dist_f[nb] + d < best:
                    best = dist_f[nb] + d
                    meet = nb
    if meet < 0:
        return None
    path = extract_parent(parent_f, start, meet)
    if path is None:
        return None
    if meet != goal:
        cur = parent_b[meet]
        while cur != goal:
            path.append(cur)
            cur = parent_b[cur]
        path.append(goal)
    return path
