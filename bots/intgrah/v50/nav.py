from __future__ import annotations

from collections import deque

from builder.state import COST_IMPASSABLE, COST_ROAD, State

_INF = 1_000_000
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
_DIAL_MOD = 14
_NODE_BUDGET = 700


def find_path(state: State, gx: int, gy: int) -> list[int] | None:
    w, h = state.w, state.h
    n = w * h
    si = state.pos.y * w + state.pos.x
    gi = gy * w + gx
    if si == gi:
        return [si]

    ht = _build_h(n, w, gx, gy)
    nb = _build_nb(state, w, h, n)
    dist = [_INF] * n
    parent = [-1] * n

    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(_DIAL_MOD)]
    f0 = ht[si]
    bk[f0 % _DIAL_MOD].append(si)
    cur_f = f0
    emp = 0
    exp = 0
    best_h = _INF
    best_node = si

    while emp < _DIAL_MOD:
        bi = cur_f % _DIAL_MOD
        if not bk[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        fn = dist[node] + ht[node]
        if fn != cur_f:
            continue
        if node == gi:
            return _extract(parent, si, gi)
        exp += 1
        hv = ht[node]
        if hv < best_h:
            best_h = hv
            best_node = node
        if exp >= _NODE_BUDGET:
            return _extract(parent, si, best_node)
        gn = dist[node]
        for ni, ec in nb[node]:
            nd = gn + ec
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[(nd + ht[ni]) % _DIAL_MOD].append(ni)

    if best_h < _INF:
        return _extract(parent, si, best_node)
    return None


def _build_h(n: int, w: int, gx: int, gy: int) -> list[int]:
    h = [0] * n
    for i in range(n):
        h[i] = max(abs(i % w - gx), abs(i // w - gy)) * COST_ROAD
    return h


def _build_cost(state: State, n: int) -> list[int]:
    cost = [0] * n
    w = state.w
    for i in range(n):
        cost[i] = state.walkable(i % w, i // w)
    return cost


def _build_nb(
    state: State, w: int, h: int, n: int
) -> list[list[tuple[int, int]]]:
    cost = _build_cost(state, n)
    nb: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for i in range(n):
        if cost[i] >= COST_IMPASSABLE:
            continue
        cx, cy = i % w, i // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                c = cost[ni]
                if c < COST_IMPASSABLE:
                    if dx != 0 and dy != 0:
                        c += 1
                    nb[i].append((ni, c))
    return nb


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
