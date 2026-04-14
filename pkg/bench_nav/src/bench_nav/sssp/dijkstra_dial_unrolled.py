from collections import deque

from bench_nav.common import INF


def dijkstra_dial_unrolled(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    bk0 = deque[int]()
    bk1 = deque[int]()
    bk2 = deque[int]()
    bk3 = deque[int]()
    bk = (bk0, bk1, bk2, bk3)
    bk0.append(start)
    cur_d = 0
    while bk0 or bk1 or bk2 or bk3:
        bki = bk[cur_d & 0b11]
        if bki:
            popleft = bki.popleft
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                for nb in pnb[node]:
                    nd = cur_d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bk[nd & 0b11].append(nb)
        cur_d += 1
    return dist
