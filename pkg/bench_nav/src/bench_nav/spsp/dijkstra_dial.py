from __future__ import annotations

from collections import deque

from bench_nav.common import CE, INF, Path_, extract_dist

assert CE + 1 == 4


def dijkstra_dial(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    """Noparent + drain loop + inlined bi + no g_node alias."""
    dist: list[int] = [INF] * n
    dist[start] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(start)
    cur_d = 0
    emp = 0
    found = False
    while emp < 4:
        bki = bk[cur_d & 0b11]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                if node == goal:
                    found = True
                    break
                for nb in pnb[node]:
                    nd = cur_d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bk[nd & 0b11].append(nb)
            if found:
                break
        else:
            emp += 1
        cur_d += 1
    if not found:
        return None
    return extract_dist(dist, cost, pnb, start, goal)
