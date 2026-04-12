from __future__ import annotations

from collections import deque

from bench_nav.common import Path_, extract_parent


def bfs(n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
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
    return extract_parent(parent, start, goal)
