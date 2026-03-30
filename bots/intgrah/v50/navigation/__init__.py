from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.state import State

from config import USE_C_NAV

from navigation.astar_bucket import find_path_raw as _py_find_path_raw

find_path_raw = _py_find_path_raw
if USE_C_NAV:
    try:
        from navigation._astar_bucket_c import find_path_raw as _c_find_path_raw

        find_path_raw = _c_find_path_raw
    except ImportError:
        pass

__all__ = ["find_path", "find_path_raw"]


def find_path(state: State, gx: int, gy: int) -> list[int] | None:
    w, h = state.w, state.h
    n = w * h
    cost = [0] * n
    for i in range(n):
        cost[i] = state.walkable(i % w, i // w)
    return find_path_raw(w, h, cost, state.pos.x, state.pos.y, gx, gy)
