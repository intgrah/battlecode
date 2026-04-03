from __future__ import annotations

from typing import TYPE_CHECKING

from util import COST_DANGER, COST_ROAD, DIAL_MOD, INF

if TYPE_CHECKING:
    from collections import deque

    from builder.state import State

NODE_BUDGET = 700


def find_path_raw(
    state: State,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    cost: list[int],
    danger: set[int] | None = None,
) -> list[int] | None:
    w = state.w
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    dist: list[int] = state.nav_dist
    parent: list[int] = state.nav_parent
    heuristic: list[int] = state.nav_heuristic
    buckets: list[deque[int]] = state.nav_buckets

    touched: list[int] = []

    h_si = max(abs(sx - gx), abs(sy - gy)) * COST_ROAD
    dist[si] = 0
    heuristic[si] = h_si
    buckets[h_si % DIAL_MOD].append(si)
    touched.append(si)

    cur_f = h_si
    emp = 0
    exp = 0
    best_h = INF
    best_node = si

    nb = state.pnb

    while emp < DIAL_MOD:
        bi = cur_f % DIAL_MOD
        if not buckets[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node = buckets[bi].popleft()
        h_node = heuristic[node]
        if dist[node] + h_node != cur_f:
            continue
        if node == gi:
            path = extract_path(parent, si, gi)
            break
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if exp >= NODE_BUDGET:
            path = extract_path(parent, si, best_node)
            break

        gn = dist[node]

        for ni in nb[node]:
            c = cost[ni]
            if danger and ni in danger:
                c += COST_DANGER
            nd = gn + c
            if nd < dist[ni]:
                if dist[ni] == INF:
                    touched.append(ni)
                dist[ni] = nd
                parent[ni] = node
                h_ni = heuristic[ni]
                if h_ni < 0:
                    nx = ni % w
                    h_ni = max(abs(nx - gx), abs(ni // w - gy)) * COST_ROAD
                    heuristic[ni] = h_ni
                buckets[(nd + h_ni) % DIAL_MOD].append(ni)
    else:
        path = extract_path(parent, si, best_node) if best_h < INF else None

    # Cleanup
    for i in touched:
        dist[i] = INF
        parent[i] = -1
        heuristic[i] = -1

    for b in buckets:
        b.clear()

    return path


def extract_path(parent: list[int], si: int, node: int) -> list[int] | None:
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur = node
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path
