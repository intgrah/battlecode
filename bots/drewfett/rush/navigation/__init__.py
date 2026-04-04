from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.state import State

from . import astar_bucket, bfs

__all__ = ["find_path", "update_bfs", "find_path_bfs"]

update_bfs = bfs.update_bfs
find_path_bfs = bfs.find_path


def find_path(
    state: State, gx: int, gy: int, ct: object | None = None
) -> list[int] | None:
    cost = state.cost
    danger = state.danger_zones
    sx, sy = state.pos.x, state.pos.y
    return astar_bucket.find_path_raw(state, sx, sy, gx, gy, cost, danger, ct=ct)
