from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from bench_nav.common import CR, INF, Path_

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def spsp_gbfs(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    w, n, pnb = md.w, md.n, md.pnb
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
    parent: list[int] = [-1] * n
    parent[si] = si
    visited: list[bool] = [False] * n
    visited[si] = True
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * CR
    heap: list[tuple[int, int]] = [(h_si, si)]
    exp = 0
    best_h = INF
    best_node = si
    while heap:
        h_node, node = heapq.heappop(heap)
        if node == gi:
            best_node = gi
            break
        if not visited[node]:
            continue
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if budget > 0 and exp >= budget:
            break
        for ni in pnb[node]:
            if visited[ni]:
                continue
            visited[ni] = True
            parent[ni] = node
            h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
            heapq.heappush(heap, (h_ni, ni))
    if best_node == si or parent[best_node] == -1:
        return None
    path: list[int] = []
    cur = best_node
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path
