from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from util import INF

if TYPE_CHECKING:
    from builder.state import State


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

    if state is not None and state.nav_parent is not None:
        parent: list[int] = state.nav_parent
        for i in state.nav_touched:
            parent[i] = -1
    else:
        parent = [-1] * n
        if state is not None:
            state.nav_parent = parent

    touched = [si]
    parent[si] = si
    q: deque[int] = deque([si])
    found = False
    nb = state.pnb if state is not None else _build_nb(w, h, n, cost)

    while q:
        node = q.popleft()
        for ni in nb[node]:
            if parent[ni] != -1:
                continue
            parent[ni] = node
            touched.append(ni)
            if ni == gi:
                found = True
                break
            q.append(ni)
        if found:
            break

    if state is not None:
        state.nav_touched = touched

    if not found:
        return None
    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path


def _build_nb(w: int, h: int, n: int, cost: list[int]) -> list[list[int]]:
    dirs = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
    nb: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        if cost[i] >= INF:
            continue
        cx, cy = i % w, i // w
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if cost[ni] < INF:
                    nb[i].append(ni)
    return nb
