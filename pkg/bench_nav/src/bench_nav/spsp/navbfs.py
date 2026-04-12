from __future__ import annotations

from bench_nav.common import INF, Path_


def navbfs(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    pnb_navbfs_push: list[list[int]],
    pnb_navbfs_set: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    """Mirrors bots/adgato/bfs_test/bfs.py::_bfs_compute.

    Uses precomputed pnb_push/pnb_set split: cardinals bracketed by two
    passable diagonals don't get enqueued (they're reached one level later
    via the diagonal expansion). dist initialized to INF, fused visited
    check, growable queue iterated with `for node in q`.
    """
    pnb_push = pnb_navbfs_push
    pnb_set = pnb_navbfs_set
    dist = [INF] * n
    dist[start] = 0
    q = [start]
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
                q.append(nb)
        for nb in pnb_set[node]:
            if d < dist[nb]:
                if nb == goal:
                    stop_at = d + 1
                dist[nb] = d
    if dist[goal] >= INF:
        return None
    path = [goal]
    cur = goal
    while cur != start:
        d = dist[cur]
        best = -1
        best_cost = INF + 1
        for nb in pnb[cur]:
            if dist[nb] == d - 1 and cost[nb] < best_cost:
                best = nb
                best_cost = cost[nb]
        if best == -1:
            return None
        path.append(best)
        cur = best
    path.reverse()
    return path
