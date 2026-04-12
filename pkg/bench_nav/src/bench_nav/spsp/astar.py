from __future__ import annotations

import heapq
from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import CE, CR, INF, Path_, extract_parent

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def spsp_astar_heap_cheb(
    md: MapData,
    si: int,
    gi: int,
    weight: int = 1,
    budget: int = 0,
) -> Path_:
    w, n, cost, pnb = md.w, md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
    g: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    g[si] = 0
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * CR
    heap: list[tuple[int, int, int]] = [(h_si * weight, h_si, si)]
    exp = 0
    best_h = INF
    best_node = si
    while heap:
        f, _, node = heapq.heappop(heap)
        if node == gi:
            return extract_parent(parent, si, gi)
        h_node = max(abs(node % w - gx), abs(node // w - gy)) * CR
        if f > g[node] + h_node * weight:
            continue
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if budget > 0 and exp >= budget:
            return extract_parent(parent, si, best_node)
        gn = g[node]
        for ni in pnb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < g[ni]:
                g[ni] = nd
                parent[ni] = node
                h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
                heapq.heappush(heap, (nd + h_ni * weight, h_ni, ni))
    if best_h < INF:
        return extract_parent(parent, si, best_node)
    return None


def spsp_astar_dial_cheb(
    md: MapData,
    si: int,
    gi: int,
    weight: int = 1,
    budget: int = 0,
) -> Path_:
    w, n, cost, pnb = md.w, md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
    mod = CE + weight + 1
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    ht: list[int] = [-1] * n
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * CR
    ht[si] = h_si
    ht[gi] = 0
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[h_si * weight % mod].append(si)
    cur_f = h_si * weight
    emp = 0
    exp = 0
    best_h = INF
    best_node = si
    while emp < mod:
        bi = cur_f % mod
        if not bk[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        h_node = ht[node]
        if dist[node] + h_node * weight != cur_f:
            continue
        if node == gi:
            return extract_parent(parent, si, gi)
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if budget > 0 and exp >= budget:
            return extract_parent(parent, si, best_node)
        gn = dist[node]
        for ni in pnb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                h_ni = ht[ni]
                if h_ni < 0:
                    h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
                    ht[ni] = h_ni
                bk[(nd + h_ni * weight) % mod].append(ni)
    if best_h < INF:
        return extract_parent(parent, si, best_node)
    return None


def _bfs_dist(n: int, pnb: list[list[int]], si: int) -> list[int]:
    """BFS hop-count distances from si. Same logic as sssp_bfs."""
    dist: list[int] = [INF] * n
    dist[si] = 0
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        d1 = dist[node] + 1
        for ni in pnb[node]:
            if dist[ni] != INF:
                continue
            dist[ni] = d1
            q.append(ni)
    return dist


def spsp_astar_dial_bfs(md: MapData, si: int, gi: int) -> Path_:
    """A* (dial's) from goal to start, using precomputed BFS heuristic."""
    if si == gi:
        return [si]
    cost, pnb = md.cost, md.pnb

    h = md.bfs_h_cache[si]

    # A* from goal to start using dial's bucket queue (noparent2 style)
    # Heuristic is consistent: |h[u]-h[v]| <= 1 <= cost(u,v) for adjacent u,v
    # Max f-increase per step = CE + 1 = 4, so mod 5 buckets
    mod = CE + 2
    g: list[int] = [INF] * md.n
    g[gi] = 0
    h_gi = h[gi]
    if h_gi >= INF:
        return None
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[h_gi % mod].append(gi)
    cur_f = h_gi
    emp = 0
    found = False
    while emp < mod:
        bki = bk[cur_f % mod]
        if not bki:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        popleft = bki.popleft
        while bki:
            node = popleft()
            gn = g[node]
            if gn + h[node] != cur_f:
                continue
            if node == si:
                found = True
                break
            for ni in pnb[node]:
                nd = gn + cost[ni]
                if nd < g[ni]:
                    g[ni] = nd
                    bk[(nd + h[ni]) % mod].append(ni)
        if found:
            break
        cur_f += 1
    if not found:
        return None
    # Extract path from si to gi by backtracking through g-values
    path = [si]
    cur = si
    while cur != gi:
        d = g[cur]
        for ni in pnb[cur]:
            if g[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    return path
