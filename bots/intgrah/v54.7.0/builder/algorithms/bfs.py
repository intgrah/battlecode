from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Position
from util.constants import INF, MAX_WIDTH

if TYPE_CHECKING:
    from builder import Builder

__all__ = ["extract_path", "update_bfs"]


def update_bfs(self: Builder, sx: int, sy: int) -> None:
    pnb = self.pnb
    dist = self.bfs_dist
    dist[:] = self.bfs_reset
    si = sy * MAX_WIDTH + sx
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
    dist = self.bfs_dist
    pnb = self.pnb
    si = sy * MAX_WIDTH + sx
    gi = gy * MAX_WIDTH + gx

    if dist[gi] == INF:
        return None

    path = [Position(gx, gy)]
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
        path.append(Position(best_i % MAX_WIDTH, best_i // MAX_WIDTH))
        ci = best_i
    path.reverse()
    return path
