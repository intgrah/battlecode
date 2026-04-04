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
    ct: object | None = None,
) -> list[int] | None:
    w = state.w
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    dist: list[int] = state.nav_dist
    parent: list[int] = state.nav_parent
    gen = state._nav_gen
    g = state._nav_g + 1
    if g > 250:
        g = 1
        for i in range(len(gen)):
            gen[i] = 0
    state._nav_g = g

    buckets: list[deque[int]] = state.nav_buckets

    h_si = max(abs(sx - gx), abs(sy - gy)) * COST_ROAD
    dist[si] = 0
    gen[si] = g
    buckets[h_si % DIAL_MOD].append(si)

    cur_f = h_si
    emp = 0
    exp = 0
    best_h = INF
    best_node = si

    nb = state.pnb
    # Pre-cache danger as local check
    has_danger = bool(danger)

    while emp < DIAL_MOD:
        bi = cur_f % DIAL_MOD
        if not buckets[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node = buckets[bi].popleft()
        gn = dist[node]
        # Compute h inline
        nx_n = node % w
        ny_n = node // w
        h_node = max(abs(nx_n - gx), abs(ny_n - gy)) * COST_ROAD
        if gn + h_node != cur_f:
            continue
        if node == gi:
            return _extract(parent, si, gi)
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if exp >= NODE_BUDGET:
            return _extract(parent, si, best_node)

        base = node * 8
        for j in range(8):
            ni = nb[base + j]
            if ni == -1:
                break
            c = cost[ni]
            if has_danger and ni in danger:
                c += COST_DANGER
            nd = gn + c
            if gen[ni] != g:
                gen[ni] = g
                dist[ni] = nd
                parent[ni] = node
                h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * COST_ROAD
                buckets[(nd + h_ni) % DIAL_MOD].append(ni)
            elif nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * COST_ROAD
                buckets[(nd + h_ni) % DIAL_MOD].append(ni)

    if best_h < INF:
        return _extract(parent, si, best_node)

    for b in buckets:
        b.clear()
    return None


def _extract(parent: list[int], si: int, node: int) -> list[int] | None:
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur = node
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path
