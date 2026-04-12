from collections import deque

from bench_nav.common import Path_, extract_parent


def bfs(n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
    parent = [-1] * n
    parent[start] = start
    q = deque([start])
    while q:
        node = q.popleft()
        for nb in pnb[node]:
            if parent[nb] == -1:
                parent[nb] = node
                if nb == goal:
                    return extract_parent(parent, start, goal)
                q.append(nb)
    return None
