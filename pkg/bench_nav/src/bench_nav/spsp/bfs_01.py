from collections import deque

from bench_nav.common import CR, Path_, extract_parent

assert CR == 1


def bfs_01(
    n: int, cost: list[int], pnb: list[list[int]], start: int, goal: int
) -> Path_:
    parent = [-1] * n
    parent[start] = start
    q = deque([start])
    popleft = q.popleft
    appendleft = q.appendleft
    append = q.append
    while q:
        node = popleft()
        if node == goal:
            return extract_parent(parent, start, goal)
        for nb in pnb[node]:
            if parent[nb] == -1:
                parent[nb] = node
                if cost[nb] == 1:
                    appendleft(nb)
                else:
                    append(nb)
    return None
