from collections import deque

from bench_nav.common import CE, CR, INF, Path_, extract_dist

assert CR == 1
assert CE == 3


def dijkstra_dial_dual(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    pnb1: list[list[int]],
    pnb3: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    dist: list[int] = [INF] * n
    dist[start] = 0
    bk = [deque[int]() for _ in range(4)]
    bk[0].append(start)
    cur_d = 0
    emp = 0
    found = False
    while emp < 4:
        bki = bk[cur_d & 3]
        if bki:
            emp = 0
            popleft = bki.popleft
            nd1 = cur_d + 1
            bk1_append = bk[nd1 & 3].append
            nd3 = cur_d + 3
            bk3_append = bk[nd3 & 3].append
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                if node == goal:
                    found = True
                    break
                for nb in pnb1[node]:
                    if nd1 < dist[nb]:
                        dist[nb] = nd1
                        bk1_append(nb)
                for nb in pnb3[node]:
                    if nd3 < dist[nb]:
                        dist[nb] = nd3
                        bk3_append(nb)
            if found:
                break
        else:
            emp += 1
        cur_d += 1
    if not found:
        return None
    return extract_dist(dist, cost, pnb, start, goal)
