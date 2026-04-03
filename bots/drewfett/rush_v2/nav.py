"""A* bucket pathfinding (Dial's algorithm).

Single standalone module — no navigation package, no backends, no config.
Port of ``bots/drewfett/rush/navigation/astar_bucket.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from util import COST_DANGER, COST_ROAD, DIAL_MOD, INF

if TYPE_CHECKING:
    from collections import deque

    from state import State

NODE_BUDGET: int = 700


def find_path(state: State, gx: int, gy: int) -> list[int] | None:
    """Find a path from ``state.pos`` to ``(gx, gy)`` using Dial's algorithm.

    Uses pre-allocated arrays on *state* (``nav_dist``, ``nav_parent``,
    ``nav_heuristic``, ``nav_buckets``) so there is zero per-call allocation
    for the search structures.

    Returns a list of flat tile indices (``y * w + x``) from start to goal,
    or ``None`` if no path is reachable within ``NODE_BUDGET`` expansions.
    """
    w: int = state.w
    sx: int = state.pos.x
    sy: int = state.pos.y
    si: int = sy * w + sx
    gi: int = gy * w + gx

    if si == gi:
        return [si]

    dist: list[int] = state.nav_dist
    parent: list[int] = state.nav_parent
    heuristic: list[int] = state.nav_heuristic
    buckets: list[deque[int]] = state.nav_buckets
    cost: list[int] = state.cost
    nb: list[list[int]] = state.pnb
    danger: set[int] = state.danger_zones

    touched: list[int] = []

    h_si: int = max(abs(sx - gx), abs(sy - gy)) * COST_ROAD
    dist[si] = 0
    heuristic[si] = h_si
    buckets[h_si % DIAL_MOD].append(si)
    touched.append(si)

    cur_f: int = h_si
    emp: int = 0
    exp: int = 0
    best_h: int = INF
    best_node: int = si

    path: list[int] | None = None

    while emp < DIAL_MOD:
        bi: int = cur_f % DIAL_MOD
        if not buckets[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0

        node: int = buckets[bi].popleft()
        h_node: int = heuristic[node]

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

        gn: int = dist[node]

        for ni in nb[node]:
            c: int = cost[ni]
            if danger and ni in danger:
                c += COST_DANGER
            nd: int = gn + c
            if nd < dist[ni]:
                if dist[ni] == INF:
                    touched.append(ni)
                dist[ni] = nd
                parent[ni] = node
                h_ni: int = heuristic[ni]
                if h_ni < 0:
                    nx: int = ni % w
                    h_ni = max(abs(nx - gx), abs(ni // w - gy)) * COST_ROAD
                    heuristic[ni] = h_ni
                buckets[(nd + h_ni) % DIAL_MOD].append(ni)
    else:
        path = extract_path(parent, si, best_node) if best_h < INF else None

    # Cleanup: reset every touched tile so arrays are clean for next call.
    for i in touched:
        dist[i] = INF
        parent[i] = -1
        heuristic[i] = -1

    for b in buckets:
        b.clear()

    return path


def extract_path(parent: list[int], si: int, node: int) -> list[int] | None:
    """Walk *parent* links from *node* back to *si* and return the forward path."""
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur: int = node
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path
