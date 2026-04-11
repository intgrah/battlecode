from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from cambc import Position

if TYPE_CHECKING:
    from builder.state import State

__all__ = ["extract_path", "update_bfs"]


def update_bfs(state: State, sx: int, sy: int) -> None:
    w = state.w
    pnb = state.pnb
    dist = state.bfs_dist
    n = w * state.h

    for i in range(n):
        dist[i] = -1

    si = sy * w + sx
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


def extract_path(
    state: State, sx: int, sy: int, gx: int, gy: int
) -> list[Position] | None:
    w = state.w
    dist = state.bfs_dist
    si = sy * w + sx
    gi = gy * w + gx

    if dist[gi] == -1:
        return None
    if si == gi:
        return [Position(sx, sy)]

    pnb = state.pnb
    path: list[Position] = [Position(gx, gy)]
    ci = gi
    while ci != si:
        best_i = -1
        best_d = dist[ci]
        for ni in pnb[ci]:
            nd = dist[ni]
            if nd == -1:
                continue
            if nd < best_d:
                best_d = nd
                best_i = ni
        if best_i == -1:
            return None
        path.append(Position(best_i % w, best_i // w))
        ci = best_i
    path.reverse()

    return path
