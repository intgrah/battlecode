from collections import deque

from bench_nav.common import CR, INF, Path_, extract_parent

assert CR == 1


def bfs_01(
    n: int, cost: list[int], pnb: list[list[int]], start: int, goal: int
) -> Path_:
    dist = [INF] * n
    dist[start] = 0
    parent = [-1] * n
    parent[start] = start
    q: deque[int] = deque([start])
    while q:
        node = q.popleft()
        if node == goal:
            break
        d = dist[node]
        for nb in pnb[node]:
            w = 0 if cost[nb] == 1 else 1
            nd = d + w
            if nd < dist[nb]:
                dist[nb] = nd
                parent[nb] = node
                if w == 0:
                    q.appendleft(nb)
                else:
                    q.append(nb)
    if dist[goal] >= INF:
        return None
    return extract_parent(parent, start, goal)
