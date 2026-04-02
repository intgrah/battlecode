from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.state import State

from config import NAV, NavMode

from . import astar_apsp, astar_bucket, astar_landmarks, bfs

__all__ = ["find_path"]

print(f"[nav] {NAV.name}")


def find_path(state: State, gx: int, gy: int) -> list[int] | None:
    cost = state.cost
    sx, sy = state.pos.x, state.pos.y

    match NAV:
        case NavMode.ASTAR_BUCKET:
            return astar_bucket.find_path_raw(state, sx, sy, gx, gy, cost)
        case NavMode.ASTAR_LANDMARKS:
            lm = state.landmarks
            if lm is not None:
                landmarks, n_tiles, lm_data = lm
                return astar_landmarks.find_path_raw(
                    state,
                    sx,
                    sy,
                    gx,
                    gy,
                    cost,
                    landmarks,
                    lm_data,
                    n_tiles,
                )
            return astar_bucket.find_path_raw(state, sx, sy, gx, gy, cost)
        case NavMode.ASTAR_APSP:
            apsp = state.apsp
            if apsp is not None:
                return astar_apsp.find_path_raw(state, sx, sy, gx, gy, cost, apsp)
            return astar_bucket.find_path_raw(state, sx, sy, gx, gy, cost)
        case NavMode.BFS:
            return bfs.find_path_raw(state, sx, sy, gx, gy)
