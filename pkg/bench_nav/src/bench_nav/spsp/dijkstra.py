from __future__ import annotations

import heapq
from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import CE, CR, INF, Path_, extract_parent

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def spsp_dijkstra_heap(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    n, cost, pnb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    exp = 0
    last_node = si
    while heap:
        d, node = heapq.heappop(heap)
        if node == gi:
            return extract_parent(parent, si, gi)
        if d > dist[node]:
            continue
        last_node = node
        exp += 1
        if budget > 0 and exp >= budget:
            return extract_parent(parent, si, last_node)
        gn = dist[node]
        for ni in pnb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                heapq.heappush(heap, (nd, ni))
    return extract_parent(parent, si, last_node)


def spsp_dijkstra_dial(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    n, cost, pnb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    mod = CE + 1
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    exp = 0
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
        if node == gi:
            return extract_parent(parent, si, gi)
        exp += 1
        if budget > 0 and exp >= budget:
            return extract_parent(parent, si, node)
        gn = dist[node]
        for ni in pnb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[nd % mod].append(ni)
    return None


def spsp_dijkstra_dial_np(md: MapData, si: int, gi: int) -> Path_:
    n, cost, pnb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    dist: list[int] = [INF] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    found = False
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
        if node == gi:
            found = True
            break
        gn = cur_d
        for ni in pnb[node]:
            nd = gn + cost[ni]
            if nd < dist[ni]:
                dist[ni] = nd
                bk[nd & 3].append(ni)
    if not found:
        return None
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path


def spsp_dijkstra_dial_np_dual(md: MapData, si: int, gi: int) -> Path_:
    if si == gi:
        return [si]
    pnb1, pnb3 = md.pnb1, md.pnb3
    n = md.n
    dist: list[int] = [INF] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    found = False
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
        if node == gi:
            found = True
            break
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
    if not found:
        return None
    cost, pnb = md.cost, md.pnb
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path


def spsp_dijkstra_dial_np_dual2(md: MapData, si: int, gi: int) -> Path_:
    if si == gi:
        return [si]
    pnb1, pnb3 = md.pnb1, md.pnb3
    cr, ce = CR, CE
    n = md.n
    dist: list[int] = [INF] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    found = False
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
        if node == gi:
            found = True
            break
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
    if not found:
        return None
    cost, pnb = md.cost, md.pnb
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path


def spsp_dijkstra_dial_np2(md: MapData, si: int, gi: int) -> Path_:
    """Noparent + drain loop + inlined bi + no gn alias."""
    if si == gi:
        return [si]
    cost, pnb = md.cost, md.pnb
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    found = False
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
            if node == gi:
                found = True
                break
            for ni in pnb[node]:
                nd = cur_d + cost[ni]
                if nd < dist[ni]:
                    dist[ni] = nd
                    bk[nd & 3].append(ni)
        if found:
            break
        cur_d += 1
    if not found:
        return None
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path


def spsp_dijkstra_dial_np_dual3(md: MapData, si: int, gi: int) -> Path_:
    """Dual + drain loop + inlined bi + no gn alias."""
    if si == gi:
        return [si]
    pnb1, pnb3 = md.pnb1, md.pnb3
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    found = False
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
            if node == gi:
                found = True
                break
            for ni in pnb1[node]:
                if nd1 < dist[ni]:
                    dist[ni] = nd1
                    bk1.append(ni)
            for ni in pnb3[node]:
                if nd3 < dist[ni]:
                    dist[ni] = nd3
                    bk3.append(ni)
        if found:
            break
        cur_d += 1
    if not found:
        return None
    cost, pnb = md.cost, md.pnb
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path


def spsp_dijkstra_dial_np_dual4(md: MapData, si: int, gi: int) -> Path_:
    """dual3 + bound append methods per distance level."""
    if si == gi:
        return [si]
    pnb1, pnb3 = md.pnb1, md.pnb3
    dist: list[int] = [INF] * md.n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    found = False
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
            if node == gi:
                found = True
                break
            for ni in pnb1[node]:
                if nd1 < dist[ni]:
                    dist[ni] = nd1
                    bk1_append(ni)
            for ni in pnb3[node]:
                if nd3 < dist[ni]:
                    dist[ni] = nd3
                    bk3_append(ni)
        if found:
            break
        cur_d += 1
    if not found:
        return None
    cost, pnb = md.cost, md.pnb
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path
