from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Position
from util import INF

if TYPE_CHECKING:
    from builder import Builder

__all__ = ["extract_path", "update_bfs"]


def update_bfs(self: Builder, sx: int, sy: int) -> None:
    w = self.w
    pnb = self.pnb
    dist = self.bfs_dist
    n = w * self.h

    for i in range(n):
        dist[i] = INF

    si = sy * w + sx
    dist[si] = 0

    q = [si]
    append = q.append
    for node in q:
        d1 = dist[node] + 1
        for ni in pnb[node]:
            if dist[ni] == INF:
                dist[ni] = d1
                append(ni)


def extract_path(
    self: Builder,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
) -> list[Position] | None:
    w = self.w
    dist = self.bfs_dist
    si = sy * w + sx
    gi = gy * w + gx

    if dist[gi] == INF:
        return None
    if si == gi:
        return [Position(sx, sy)]

    pnb = self.pnb
    path: list[Position] = [Position(gx, gy)]
    ci = gi
    while ci != si:
        best_i = -1
        best_d = dist[ci]
        for ni in pnb[ci]:
            nd = dist[ni]
            if nd < best_d:
                best_d = nd
                best_i = ni
        if best_i == -1:
            return None
        path.append(Position(best_i % w, best_i // w))
        ci = best_i
    path.reverse()
    return path
