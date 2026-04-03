from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import State


def update_bfs(state: State) -> None:
    w = state.w
    n = w * state.h
    pos = state.pos
    si = pos.y * w + pos.x
    pnb = state.pnb
    parent = state.nav_parent
    dist = state.nav_dist

    for i in range(n):
        parent[i] = -1
        dist[i] = -1

    parent[si] = si
    dist[si] = 0

    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        d = dist[node] + 1
        for ni in pnb[node]:
            if parent[ni] != -1:
                continue
            parent[ni] = node
            dist[ni] = d
            q.append(ni)
