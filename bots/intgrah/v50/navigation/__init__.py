from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.state import State

from config import NAV, NavMode

from navigation.astar_apsp import find_path_raw as _apsp
from navigation.astar_bucket import find_path_raw as _bucket_py
from navigation.astar_landmarks import find_path_raw as _landmarks

_bucket_c = _bucket_py
if NAV == NavMode.ASTAR_BUCKET_C:
    try:
        from navigation._astar_bucket_c import find_path_raw as _bucket_c

        _BACKEND = NavMode.ASTAR_BUCKET_C
    except ImportError:
        _BACKEND = NavMode.ASTAR_BUCKET_PYTHON
else:
    _BACKEND = NAV

print(f"[nav] {_BACKEND.name}")

__all__ = ["find_path"]


def find_path(state: State, gx: int, gy: int) -> list[int] | None:
    w, h = state.w, state.h
    cost = state.cost
    sx, sy = state.pos.x, state.pos.y

    match _BACKEND:
        case NavMode.ASTAR_BUCKET_C:
            return _bucket_c(w, h, cost, sx, sy, gx, gy)
        case NavMode.ASTAR_BUCKET_PYTHON:
            return _bucket_py(w, h, cost, sx, sy, gx, gy)
        case NavMode.ASTAR_LANDMARKS:
            lm = state.landmarks
            if lm is not None:
                landmarks, n_tiles, lm_data = lm
                return _landmarks(
                    w,
                    h,
                    cost,
                    sx,
                    sy,
                    gx,
                    gy,
                    landmarks,
                    lm_data,
                    n_tiles,
                )
            return _bucket_py(w, h, cost, sx, sy, gx, gy)
        case NavMode.ASTAR_APSP:
            apsp = state.apsp
            if apsp is not None:
                return _apsp(w, h, cost, sx, sy, gx, gy, apsp)
            return _bucket_py(w, h, cost, sx, sy, gx, gy)
