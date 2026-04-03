from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import State


def update_bfs(state: State) -> None:
    w = state.w
    pos = state.pos
    si = pos.y * w + pos.x
    pnb = state.pnb
    parent = state.nav_parent
    dist = state.nav_dist
    blocked = {p.y * w + p.x for p in state.unit_tiles}

    # Reset from previous turn
    for i in state._bfs_touched:
        parent[i] = -1
        dist[i] = -1

    touched: list[int] = [si]
    parent[si] = si
    dist[si] = 0

    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        d = dist[node] + 1
        for ni in pnb[node]:
            if parent[ni] != -1:
                continue
            if ni in blocked:
                continue
            parent[ni] = node
            dist[ni] = d
            touched.append(ni)
            q.append(ni)

    state._bfs_touched = touched
