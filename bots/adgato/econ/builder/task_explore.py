"""Enemy-biased exploration.

Picks unseen tiles biased toward the enemy half of the map. If the
enemy core position is known, bias toward it; otherwise, bias toward
the opposite side of the map from our core.

Commitment: once a target is picked, it persists until the tile is seen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .action import Action
    from .state import State


def _enemy_direction(state: State) -> tuple[int, int]:
    """Target point toward likely enemy core."""
    if state.en_core_pos is not None:
        return state.en_core_pos.x, state.en_core_pos.y
    cx, cy = state.my_core.x, state.my_core.y
    return state.w - 1 - cx, state.h - 1 - cy


def explore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x,
        state.explore_target.y,
    ):
        state.explore_target = None

    if state.explore_target is None:
        state.explore_target = _pick_target(state)
    if state.explore_target is None:
        return None

    result = move_toward_with_road(state, ct, state.explore_target)
    if result is None:
        return None
    ct.draw_indicator_dot(state.explore_target, 0, 0, 255)
    return result


def _pick_target(state: State) -> Position | None:
    """Pick the best unseen tile biased toward enemy half."""
    w = state.w
    h = state.h
    pos = state.pos
    enemy_x, enemy_y = _enemy_direction(state)
    max_dim = max(w, h)

    best: Position | None = None
    best_score = -1_000_000

    for y in range(0, h, 3):
        for x in range(0, w, 3):
            if not state.is_unseen(x, y):
                continue
            walk_dist = max(abs(pos.x - x), abs(pos.y - y))
            enemy_dist = max(abs(enemy_x - x), abs(enemy_y - y))
            closeness = max_dim - enemy_dist
            score = -walk_dist + closeness * 0.5
            if score > best_score:
                best_score = score
                best = Position(x, y)

    return best
