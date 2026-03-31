from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from util import COST_ROAD, DIR8_DELTA, INF

if TYPE_CHECKING:
    from hardcode.apsp_loader import ApspTable

_NODE_BUDGET = 700


def find_path_raw(
    w: int,
    h: int,
    cost: list[int],
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    apsp: ApspTable,
) -> list[int] | None:
    n = w * h
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    g = [INF] * n
    parent = [-1] * n
    g[si] = 0
    touched = [si]
    h0 = apsp.dist(si, gi)
    h0 = h0 * COST_ROAD if h0 < 255 else INF
    heap: list[tuple[int, int, int]] = [(h0, h0, si)]
    exp = 0
    best_h = INF
    best_node = si

    while heap:
        f, _, node = heapq.heappop(heap)
        if node == gi:
            return _extract(parent, si, gi)
        hv = apsp.dist(node, gi)
        hv = hv * COST_ROAD if hv < 255 else INF
        if f > g[node] + hv:
            continue
        exp += 1
        if hv < best_h:
            best_h = hv
            best_node = node
        if exp >= _NODE_BUDGET:
            return _extract(parent, si, best_node)
        gn = g[node]
        cx, cy = node % w, node // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            ni = ny * w + nx
            c = cost[ni]
            if c >= INF:
                continue
            nd = gn + c
            if nd < g[ni]:
                if g[ni] == INF:
                    touched.append(ni)
                g[ni] = nd
                parent[ni] = node
                h_ni = apsp.dist(ni, gi)
                h_ni = h_ni * COST_ROAD if h_ni < 255 else INF
                heapq.heappush(heap, (nd + h_ni, h_ni, ni))

    if best_h < INF:
        return _extract(parent, si, best_node)
    return None


def _extract(parent: list[int], si: int, node: int) -> list[int] | None:
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur = node
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path
