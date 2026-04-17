from collections import deque

from bench_nav.common import CE, INF

assert CE + 1 == 4


def dijkstra_dial_skip_pnbc(
    n: int,
    pnb_push_c: list[list[tuple[int, int]]],
    pnb_set_c: list[list[tuple[int, int]]],
    start: int,
) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    bk = [deque[int]() for _ in range(4)]
    bk[0].append(start)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 0b11]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                for nb, c in pnb_push_c[node]:
                    nd = cur_d + c
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bk[nd & 0b11].append(nb)
                for nb, c in pnb_set_c[node]:
                    nd = cur_d + c
                    dist[nb] = min(dist[nb], nd)
        else:
            emp += 1
        cur_d += 1
    return dist
