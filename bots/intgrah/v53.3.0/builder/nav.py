from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from cambc import Position
from util import INF

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State

ROAD_COST = 3
NB = 5


def update_bfs(state: State, ct: Controller) -> None:
    w = state.w
    n = w * state.h
    pos = ct.get_position()
    si = pos.y * w + pos.x
    pnb = state.pnb
    dist = state.nav_dist

    for i in range(n):
        dist[i] = -1

    dist[si] = 0

    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        d = dist[node] + 1
        for ni in pnb[node]:
            if dist[ni] != -1:
                continue
            dist[ni] = d
            q.append(ni)


def dial_astar_first_hop(
    state: State, ct: Controller, target: Position
) -> Position | None:
    w = state.w
    n = w * state.h
    si = ct.get_position().y * w + ct.get_position().x
    gi = target.y * w + target.x
    bfs_dist = state.nav_dist
    cost = state.cost_grid
    pnb = state.pnb

    if bfs_dist[gi] < 0:
        return None

    g: list[int] = [INF] * n
    g[gi] = 0

    max_f = n * ROAD_COST
    bk: list[list[int]] = [[] for _ in range(max_f + 1)]
    f0 = bfs_dist[gi]
    if f0 > max_f:
        return None
    bk[f0].append(gi)
    cur_f = f0
    emp = 0

    while emp < NB:
        if cur_f > max_f:
            break
        if not bk[cur_f]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        for node in bk[cur_f]:
            if g[node] + bfs_dist[node] != cur_f:
                continue
            if node == si:
                best = -1
                best_g = INF
                for ni in pnb[si]:
                    if g[ni] < best_g:
                        best_g = g[ni]
                        best = ni
                if best < 0:
                    return None
                return Position(best % w, best // w)
            if ct.get_cpu_time_elapsed() > 1600:
                break
            gn = g[node]
            for ni in pnb[node]:
                c = cost[ni]
                if c >= INF:
                    continue
                ng = gn + c
                if ng < g[ni]:
                    g[ni] = ng
                    h = bfs_dist[ni]
                    if h < 0:
                        continue
                    f = ng + h
                    if f <= max_f:
                        bk[f].append(ni)
        cur_f += 1

    return None


def nav_first_hop(state: State, ct: Controller, target: Position) -> Position | None:
    hop = dial_astar_first_hop(state, ct, target)
    if hop is not None:
        return hop
    w = state.w
    gi = target.y * w + target.x
    si = ct.get_position().y * w + ct.get_position().x
    dist = state.nav_dist
    if dist[gi] < 0:
        return None
    best = -1
    best_d = INF
    for ni in state.pnb[si]:
        if dist[ni] >= 0 and dist[ni] < best_d:
            best_d = dist[ni]
            best = ni
    if best < 0:
        return None
    return Position(best % w, best // w)
