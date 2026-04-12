from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from bench_nav.common import DIR8, INF, Path_, extract_parent

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


class ApspTable:
    __slots__ = ("_rows",)

    def __init__(self, rows: list[list[int]]) -> None:
        self._rows = rows

    def dist(self, a: int, b: int) -> int:
        return self._rows[a][b]


def precompute_apsp(md: MapData) -> None:
    n, cost, pnb = md.n, md.cost, md.pnb
    rows: list[list[int]] = []
    for si in range(n):
        if cost[si] >= INF:
            rows.append([INF] * n)
            continue
        dist: list[int] = [INF] * n
        dist[si] = 0
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
                    heapq.heappush(heap, (nd, ni))
        rows.append(dist)
    md.apsp = ApspTable(rows)


def spsp_astar_heap_apsp(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    w, n, cost = md.w, md.n, md.cost
    apsp = md.apsp
    assert apsp is not None
    if si == gi:
        return [si]
    g: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    g[si] = 0
    h0 = apsp.dist(si, gi)
    heap: list[tuple[int, int, int]] = [(h0, h0, si)]
    exp = 0
    best_h = INF
    best_node = si
    while heap:
        f, _, node = heapq.heappop(heap)
        if node == gi:
            return extract_parent(parent, si, gi)
        hv = apsp.dist(node, gi)
        if f > g[node] + hv:
            continue
        exp += 1
        if hv < best_h:
            best_h = hv
            best_node = node
        if budget > 0 and exp >= budget:
            return extract_parent(parent, si, best_node)
        gn = g[node]
        cx, cy = node % w, node // w
        for dx, dy in DIR8:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= md.h:
                continue
            ni = ny * w + nx
            c = cost[ni]
            nd = gn + c
            if nd < g[ni]:
                g[ni] = nd
                parent[ni] = node
                h_ni = apsp.dist(ni, gi)
                heapq.heappush(heap, (nd + h_ni, h_ni, ni))
    if best_h < INF:
        return extract_parent(parent, si, best_node)
    return None
