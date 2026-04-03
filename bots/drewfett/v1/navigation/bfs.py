from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.state import State


def find_path_raw(
    state: State,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
) -> list[int] | None:
    w = state.w
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    parent: list[int] = state.nav_parent

    # Invariant
    assert all(p == -1 for p in parent)

    touched: list[int] = [si]
    parent[si] = si

    q: deque[int] = deque([si])
    found = False
    nb = state.pnb
    blocked = {p.y * w + p.x for p in state.unit_tiles}

    while q:
        node = q.popleft()
        for ni in nb[node]:
            # Node already visited
            if parent[ni] != -1:
                continue
            # We cannot walk over builders
            if node == si and ni in blocked:
                continue
            parent[ni] = node
            touched.append(ni)
            if ni == gi:
                found = True
                break
            q.append(ni)
        if found:
            break

    path: list[int] | None = None
    if found:
        path = []
        cur = gi
        while cur != si:
            path.append(cur)
            cur = parent[cur]
        path.append(si)
        path.reverse()

    # Cleanup
    for i in touched:
        parent[i] = -1

    # Invariant
    assert all(p == -1 for p in parent)

    return path
