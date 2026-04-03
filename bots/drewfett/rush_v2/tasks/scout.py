"""RUSH: scout enemy half to find core + ore for siege."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Position
from util import INF

if TYPE_CHECKING:
    from state import State
    from turn import Turn


def run(state: State, ct: Controller) -> Turn | None:
    """Scout near enemy core to find ore for rushing."""
    from tasks._helpers import move_toward

    en_core = state.en_core_pos
    if en_core is None:
        return None

    # If on our half and no Ti income, don't scout yet
    pos = state.pos
    my_core = state.my_core
    if pos.distance_squared(my_core) < pos.distance_squared(en_core):
        core_flow = sum(state.flow.ti[i] for i in state.my_core_tiles)
        if core_flow < 0.1:
            return None

    # Pick nearest unseen tile near enemy core
    target = _pick_target(state)
    if target is None:
        return move_toward(state, ct, en_core)

    return move_toward(state, ct, target)


def _pick_target(state: State) -> Position | None:
    """Pick nearest unseen tile to enemy core within ~15 tiles."""
    en_core = state.en_core_pos
    if en_core is None:
        return None

    w, h = state.w, state.h
    pos = state.pos
    best: Position | None = None
    best_score = INF

    ex, ey = en_core.x, en_core.y
    for dy in range(-15, 16, 2):
        for dx in range(-15, 16, 2):
            x, y = ex + dx, ey + dy
            if not (0 <= x < w and 0 <= y < h):
                continue
            if not state.is_unseen(x, y):
                continue
            walk = max(abs(pos.x - x), abs(pos.y - y))
            core_dist = max(abs(ex - x), abs(ey - y))
            score = walk + core_dist
            if score < best_score:
                best_score = score
                best = Position(x, y)

    return best
