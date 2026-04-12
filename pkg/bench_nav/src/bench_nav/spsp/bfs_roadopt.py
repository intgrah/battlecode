from collections import deque

from bench_nav.common import Path_, extract_parent


def bfs_roadopt(
    n: int, cost: list[int], pnb: list[list[int]], start: int, goal: int
) -> Path_:
    parent = [-1] * n
    parent[start] = start
    q: deque[int] = deque([start])
    found = False
    while q:
        node = q.popleft()
        for nb in pnb[node]:
            if parent[nb] != -1:
                continue
            parent[nb] = node
            if nb == goal:
                found = True
                break
            q.append(nb)
        if found:
            break
    if not found:
        return None
    path = extract_parent(parent, start, goal)
    if path is None or len(path) < 3:
        return path
    next_next = path[2]
    best_nb = path[1]
    best_cost = cost[best_nb]
    for nb in pnb[start]:
        if cost[nb] >= best_cost or parent[nb] != start:
            continue
        adjacent_to_next = False
        for nb2 in pnb[nb]:
            if nb2 == next_next:
                adjacent_to_next = True
                break
        if adjacent_to_next:
            best_nb = nb
            best_cost = cost[nb]
    path[1] = best_nb
    return path
