from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from util import COST_ROAD, INF

if TYPE_CHECKING:
    from builder.state import State
    from hardcode.apsp_loader import ApspTable

_NODE_BUDGET = 700


def find_path_raw(
    state: State,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    cost: list[int],
    apsp: ApspTable,
) -> list[int] | None:
    w = state.w
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    dist: list[int] = state.nav_dist
    parent: list[int] = state.nav_parent
    heuristic: list[int] = state.nav_heuristic

    # Invariant
    assert all(d == INF for d in dist)
    assert all(p == -1 for p in parent)
    assert all(he == -1 for he in heuristic)

    def _h(i: int) -> int:
        v = heuristic[i]
        if v >= 0:
            return v
        v = apsp.dist(i, gi)
        v = v * COST_ROAD if v < 255 else INF
        heuristic[i] = v
        return v

    nb = state.pnb
    touched: list[int] = []

    h_si = _h(si)
    dist[si] = 0
    touched.append(si)

    heap: list[tuple[int, int, int]] = [(h_si, h_si, si)]
    exp = 0
    best_h = INF
    best_node = si

    while heap:
        f, _, node = heapq.heappop(heap)
        h_node = _h(node)
        if f > dist[node] + h_node:
            continue
        if node == gi:
            path = _extract(parent, si, gi)
            break
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if exp >= _NODE_BUDGET:
            path = _extract(parent, si, best_node)
            break

        gn = dist[node]
        for ni in nb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                if dist[ni] == INF:
                    touched.append(ni)
                dist[ni] = nd
                parent[ni] = node
                h_ni = _h(ni)
                heapq.heappush(heap, (nd + h_ni, h_ni, ni))
    else:
        path = _extract(parent, si, best_node) if best_h < INF else None

    # Cleanup
    for i in touched:
        dist[i] = INF
        parent[i] = -1
        heuristic[i] = -1

    # Invariant
    assert all(d == INF for d in dist)
    assert all(p == -1 for p in parent)
    assert all(he == -1 for he in heuristic)

    return path


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
