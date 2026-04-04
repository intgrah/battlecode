"""Forward BFS from builder position.

Runs full BFS from builder each turn, storing parent and dist for every
reachable tile. Path extraction follows parent pointers backward from goal.

Uses generation counter to avoid O(n) reset each turn.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.state import State


def update_bfs(state: State) -> None:
    """Run forward BFS from builder position. Call once per turn."""
    w = state.w
    pos = state.pos
    si = pos.y * w + pos.x
    pnb = state.pnb
    parent = state.nav_parent
    dist = state.nav_dist
    danger = state.danger_zones
    gen = state._nav_gen
    g = state._nav_g + 1
    if g > 250:
        g = 1
        for i in range(len(gen)):
            gen[i] = 0
    state._nav_g = g

    parent[si] = si
    dist[si] = 0
    gen[si] = g

    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        d = dist[node] + 1
        base = node * 8
        for j in range(8):
            ni = pnb[base + j]
            if ni == -1:
                break
            if gen[ni] == g:
                continue
            if ni in danger:
                continue
            gen[ni] = g
            parent[ni] = node
            dist[ni] = d
            q.append(ni)


def find_path(state: State, gx: int, gy: int) -> list[int] | None:
    """Extract path from BFS parent pointers. Goal → start, then reverse."""
    w = state.w
    si = state.pos.y * w + state.pos.x
    gi = gy * w + gx
    if si == gi:
        return [si]

    g = state._nav_g
    gen = state._nav_gen
    if gen[gi] != g:
        return None

    parent = state.nav_parent
    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path
