from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from util import COST_ROAD, INF

if TYPE_CHECKING:
    from builder.state import State

_DIAL_MOD = 14
_NODE_BUDGET = 700


def find_path_raw(
    w: int,
    h: int,
    cost: list[int],
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    state: State | None = None,
) -> list[int] | None:
    n = w * h
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    offsets_card = (-w, -1, 1, w)
    offsets_diag = (-w - 1, -w + 1, w - 1, w + 1)

    if state is not None and state.nav_dist is not None:
        dist: list[int] = state.nav_dist
        parent: list[int] = state.nav_parent  # type: ignore[assignment]
        ht: list[int] = state.nav_ht  # type: ignore[assignment]
        bk: list[deque[int]] = state.nav_bk  # type: ignore[assignment]
        for i in state.nav_touched:
            dist[i] = INF
            parent[i] = -1
            ht[i] = -1
        for d in bk:
            d.clear()
    else:
        dist = [INF] * n
        parent = [-1] * n
        ht = [-1] * n
        bk = [deque() for _ in range(_DIAL_MOD)]
        if state is not None:
            state.nav_dist = dist
            state.nav_parent = parent
            state.nav_ht = ht
            state.nav_bk = bk

    touched = [si, gi]
    h_si = max(abs(sx - gx), abs(sy - gy)) * COST_ROAD
    ht[si] = h_si
    ht[gi] = 0
    dist[si] = 0
    bk[h_si % _DIAL_MOD].append(si)
    cur_f = h_si
    emp = 0
    exp = 0
    best_h = INF
    best_node = si

    while emp < _DIAL_MOD:
        bi = cur_f % _DIAL_MOD
        if not bk[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        h_node = ht[node]
        if dist[node] + h_node != cur_f:
            continue
        if node == gi:
            if state is not None:
                state.nav_touched = touched
            return _extract(parent, si, gi)
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if exp >= _NODE_BUDGET:
            if state is not None:
                state.nav_touched = touched
            return _extract(parent, si, best_node)
        gn = dist[node]
        cx = node % w
        at_left = cx == 0
        at_right = cx == w - 1

        for off in offsets_card:
            ni = node + off
            if 0 <= ni < n:
                if off == -1 and at_left:
                    continue
                if off == 1 and at_right:
                    continue
                c = cost[ni]
                if c < INF:
                    nd = gn + c
                    if nd < dist[ni]:
                        if dist[ni] == INF:
                            touched.append(ni)
                        dist[ni] = nd
                        parent[ni] = node
                        h_ni = ht[ni]
                        if h_ni < 0:
                            nx = ni % w
                            h_ni = max(abs(nx - gx), abs(ni // w - gy)) * COST_ROAD
                            ht[ni] = h_ni
                        bk[(nd + h_ni) % _DIAL_MOD].append(ni)

        for off in offsets_diag:
            ni = node + off
            if 0 <= ni < n:
                if (off == -w - 1 or off == w - 1) and at_left:
                    continue
                if (off == -w + 1 or off == w + 1) and at_right:
                    continue
                c = cost[ni]
                if c < INF:
                    nd = gn + c + 1
                    if nd < dist[ni]:
                        if dist[ni] == INF:
                            touched.append(ni)
                        dist[ni] = nd
                        parent[ni] = node
                        h_ni = ht[ni]
                        if h_ni < 0:
                            nx = ni % w
                            h_ni = max(abs(nx - gx), abs(ni // w - gy)) * COST_ROAD
                            ht[ni] = h_ni
                        bk[(nd + h_ni) % _DIAL_MOD].append(ni)

    if state is not None:
        state.nav_touched = touched
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
