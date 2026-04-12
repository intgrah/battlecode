from __future__ import annotations

import heapq
from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import CE, CR, INF

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def sssp_dijkstra_heap(md: MapData, si: int) -> list[int]:
    n, cost, pnb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni in pnb[node]:
            c = cost[ni]
            nd = d + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                heapq.heappush(heap, (nd, ni))
    return parent


def sssp_dijkstra_dial(md: MapData, si: int) -> list[int]:
    n, cost, pnb = md.n, md.cost, md.pnb
    mod = CE + 1
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < mod:
        bi = cur_d % mod
        if not bk[bi]:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        if dist[node] != cur_d:
            continue
        gn = dist[node]
        for ni in pnb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[nd % mod].append(ni)
    return parent


def sssp_dijkstra_dial_inline(md: MapData, si: int) -> list[int]:
    n, cost, pnb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        bki = bk[bi]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bki.popleft()
        if dist[node] != cur_d:
            continue
        gn = cur_d
        for ni in pnb[node]:
            nd = gn + cost[ni]
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[nd & 3].append(ni)
    return parent


def sssp_dijkstra_dial_pnbc(md: MapData, si: int) -> list[int]:
    n, pnbc = md.n, md.pnbc
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        bki = bk[bi]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bki.popleft()
        if dist[node] != cur_d:
            continue
        gn = cur_d
        for ni, c in pnbc[node]:
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[nd & 3].append(ni)
    return parent


def sssp_dijkstra_dial_np(md: MapData, si: int) -> list[int]:
    n, cost, pnb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        bki = bk[bi]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bki.popleft()
        if dist[node] != cur_d:
            continue
        gn = cur_d
        for ni in pnb[node]:
            nd = gn + cost[ni]
            if nd < dist[ni]:
                dist[ni] = nd
                bk[nd & 3].append(ni)
    return dist


def sssp_dijkstra_dial_np_dual(md: MapData, si: int) -> list[int]:
    n = md.n
    pnb1, pnb3 = md.pnb1, md.pnb3
    dist: list[int] = [INF] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        bki = bk[bi]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bki.popleft()
        if dist[node] != cur_d:
            continue
        gn = cur_d
        nd1 = gn + CR
        for ni in pnb1[node]:
            if nd1 < dist[ni]:
                dist[ni] = nd1
                bk[nd1 & 3].append(ni)
        nd3 = gn + CE
        for ni in pnb3[node]:
            if nd3 < dist[ni]:
                dist[ni] = nd3
                bk[nd3 & 3].append(ni)
    return dist


def sssp_dijkstra_dial_np_dual2(md: MapData, si: int) -> list[int]:
    n = md.n
    pnb1, pnb3 = md.pnb1, md.pnb3
    cr, ce = CR, CE
    dist: list[int] = [INF] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 3]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bki.popleft()
        if dist[node] != cur_d:
            continue
        nd1 = cur_d + cr
        bk1_append = bk[nd1 & 3].append
        for ni in pnb1[node]:
            if nd1 < dist[ni]:
                dist[ni] = nd1
                bk1_append(ni)
        nd3 = cur_d + ce
        bk3_append = bk[nd3 & 3].append
        for ni in pnb3[node]:
            if nd3 < dist[ni]:
                dist[ni] = nd3
                bk3_append(ni)
    return dist


def sssp_dijkstra_dial_np2(md: MapData, si: int) -> list[int]:
    """Noparent + drain loop + inlined bi + no gn alias."""
    cost, pnb = md.cost, md.pnb
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 3]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        popleft = bki.popleft
        while bki:
            node = popleft()
            if dist[node] != cur_d:
                continue
            for ni in pnb[node]:
                nd = cur_d + cost[ni]
                if nd < dist[ni]:
                    dist[ni] = nd
                    bk[nd & 3].append(ni)
        cur_d += 1
    return dist


def sssp_dijkstra_dial_np_beacon(md: MapData, si: int) -> list[int]:
    """Counting sort queue: one list per distance value, preallocated."""
    cost, pnb = md.cost, md.pnb
    max_dist = md.n * 3
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[list[int]] = [[] for _ in range(max_dist)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        if not bk[cur_d]:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        for node in bk[cur_d]:
            if dist[node] != cur_d:
                continue
            for ni in pnb[node]:
                nd = cur_d + cost[ni]
                if nd < dist[ni]:
                    dist[ni] = nd
                    bk[nd].append(ni)
        cur_d += 1
    return dist


def sssp_dijkstra_dial_np_dual3(md: MapData, si: int) -> list[int]:
    """Dual + drain loop + inlined bi + no gn alias."""
    pnb1, pnb3 = md.pnb1, md.pnb3
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 3]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        popleft = bki.popleft
        nd1 = cur_d + CR
        bk1 = bk[nd1 & 3]
        nd3 = cur_d + CE
        bk3 = bk[nd3 & 3]
        while bki:
            node = popleft()
            if dist[node] != cur_d:
                continue
            for ni in pnb1[node]:
                if nd1 < dist[ni]:
                    dist[ni] = nd1
                    bk1.append(ni)
            for ni in pnb3[node]:
                if nd3 < dist[ni]:
                    dist[ni] = nd3
                    bk3.append(ni)
        cur_d += 1
    return dist


def sssp_dijkstra_dial_np_dual4(md: MapData, si: int) -> list[int]:
    """dual3 + bound append methods per distance level."""
    pnb1, pnb3 = md.pnb1, md.pnb3
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 3]
        if not bki:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        popleft = bki.popleft
        nd1 = cur_d + CR
        bk1_append = bk[nd1 & 3].append
        nd3 = cur_d + CE
        bk3_append = bk[nd3 & 3].append
        while bki:
            node = popleft()
            if dist[node] != cur_d:
                continue
            for ni in pnb1[node]:
                if nd1 < dist[ni]:
                    dist[ni] = nd1
                    bk1_append(ni)
            for ni in pnb3[node]:
                if nd3 < dist[ni]:
                    dist[ni] = nd3
                    bk3_append(ni)
        cur_d += 1
    return dist


def sssp_dijkstra_dial_np5(md: MapData, si: int) -> list[int]:
    """Noparent + drain + clean control flow (no emp)."""
    cost, pnb = md.cost, md.pnb
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk0: deque[int] = deque()
    bk1: deque[int] = deque()
    bk2: deque[int] = deque()
    bk3: deque[int] = deque()
    bks = (bk0, bk1, bk2, bk3)
    bk0.append(si)
    cur_d = 0
    while bk0 or bk1 or bk2 or bk3:
        bki = bks[cur_d & 3]
        if bki:
            popleft = bki.popleft
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                for ni in pnb[node]:
                    nd = cur_d + cost[ni]
                    if nd < dist[ni]:
                        dist[ni] = nd
                        bks[nd & 3].append(ni)
        cur_d += 1
    return dist


def sssp_dijkstra_dial_np_dual5(md: MapData, si: int) -> list[int]:
    """Dual + drain + clean control flow (no emp)."""
    pnb1, pnb3 = md.pnb1, md.pnb3
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk0: deque[int] = deque()
    bk1_: deque[int] = deque()
    bk2: deque[int] = deque()
    bk3_: deque[int] = deque()
    bks = (bk0, bk1_, bk2, bk3_)
    bk0.append(si)
    cur_d = 0
    while bk0 or bk1_ or bk2 or bk3_:
        bki = bks[cur_d & 3]
        if bki:
            popleft = bki.popleft
            nd1 = cur_d + CR
            nbk1 = bks[nd1 & 3]
            nd3 = cur_d + CE
            nbk3 = bks[nd3 & 3]
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                for ni in pnb1[node]:
                    if nd1 < dist[ni]:
                        dist[ni] = nd1
                        nbk1.append(ni)
                for ni in pnb3[node]:
                    if nd3 < dist[ni]:
                        dist[ni] = nd3
                        nbk3.append(ni)
        cur_d += 1
    return dist
