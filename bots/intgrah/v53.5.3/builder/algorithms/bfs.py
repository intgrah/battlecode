from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from cambc import Position
from util import DIR8_DELTA, INF

if TYPE_CHECKING:
    from builder.state import State


def update_bfs(state: State, sx: int, sy: int) -> None:
    w = state.w
    h = state.h
    cost = state.cost_grid
    dist = state.nav_dist
    n = w * h

    for i in range(n):
        dist[i] = -1

    si = sy * w + sx
    dist[si] = 0

    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        d = dist[node] + 1
        cx, cy = node % w, node // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if dist[ni] != -1:
                continue
            if cost[ni] >= INF:
                continue
            dist[ni] = d
            q.append(ni)


def extract_path(
    state: State, sx: int, sy: int, gx: int, gy: int
) -> list[Position] | None:
    w = state.w
    h = state.h
    dist = state.nav_dist
    cost = state.cost_grid
    si = sy * w + sx
    gi = gy * w + gx

    if dist[gi] == -1:
        return None
    if si == gi:
        return [Position(sx, sy)]

    path: list[Position] = [Position(sx, sy)]
    cx, cy = sx, sy
    visited: set[int] = {si}
    while True:
        ci = cy * w + cx
        if ci == gi:
            break
        best_i = -1
        best_d = dist[ci]
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if ni in visited:
                continue
            if cost[ni] >= INF:
                continue
            nd = dist[ni]
            if nd == -1:
                continue
            if nd < best_d:
                best_d = nd
                best_i = ni
        if best_i == -1:
            return None
        visited.add(best_i)
        cx, cy = best_i % w, best_i // w
        path.append(Position(cx, cy))

    return path
