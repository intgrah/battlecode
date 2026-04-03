from __future__ import annotations

from typing import TYPE_CHECKING

from config import DEBUG_DUMP
from visualiser import Tiles, emit

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

    parent = state.nav_parent
    if parent[gi] == -1:
        return None

    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()

    if DEBUG_DUMP:
        emit(
            bfs_path=Tiles([(i % w, i // w) for i in path]),
        )

    return path
