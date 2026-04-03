"""Role-aware exploration: pick unseen tiles and move toward them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Position
from util import INF, Role

from ._helpers import chebyshev, move_toward

if TYPE_CHECKING:
    from cambc import Controller
    from state import State
    from turn import Turn


def run(state: State, ct: Controller) -> Turn | None:
    # Clear target if we can now see it
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x, state.explore_target.y
    ):
        state.explore_target = None

    # Pick a new target if needed
    if state.explore_target is None:
        state.explore_target = _pick_target(state)

    if state.explore_target is None:
        return None

    return move_toward(state, ct, state.explore_target)


def _pick_target(state: State) -> Position | None:
    """Sample unseen tiles and pick the best one based on role."""
    w = state.w
    h = state.h
    n = w * h
    max_dim = max(w, h)

    pos = state.pos
    role = state.role

    # Estimate enemy core position (or use opposite corner)
    if state.en_core_pos is not None:
        en_x, en_y = state.en_core_pos.x, state.en_core_pos.y
    else:
        en_x = w - 1 - state.my_core.x
        en_y = h - 1 - state.my_core.y

    core_x, core_y = state.my_core.x, state.my_core.y

    best_score = -INF
    best_pos: Position | None = None

    for i in range(0, n, 3):
        if state.env[i] is not None:
            continue  # already seen
        tx, ty = i % w, i // w
        walk_dist = chebyshev(pos.x, pos.y, tx, ty)
        if walk_dist == 0:
            continue

        match role:
            case Role.RUSH:
                enemy_closeness = max_dim - chebyshev(tx, ty, en_x, en_y)
                score = -walk_dist + enemy_closeness * 0.5
            case Role.ECON | Role.HOME | _:
                home_closeness = max_dim - chebyshev(tx, ty, core_x, core_y)
                score = -walk_dist + home_closeness * 0.5

        if score > best_score:
            best_score = score
            best_pos = Position(tx, ty)

    return best_pos
