"""Exploration with role-aware strategies.

ECON (role 0): Expanding ring from core -- systematic, finds all nearby ore.
ATTACK (role 1): Bias toward enemy core -- scout enemy half.

Commitment: once a target is picked, it persists until the tile is seen.
"""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from action import Action
    from .state import State


def explore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    # Clear target if seen
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x,
        state.explore_target.y,
    ):
        state.explore_target = None

    if state.explore_target is None:
        if state.role == 0:  # ECON: expanding ring
            _advance_frontier(state)
            state.explore_target = _pick_ring_target(state)
        else:
            state.explore_target = _pick_biased_target(state)

    if state.explore_target is None:
        return None

    result = move_toward_with_road(state, ct, state.explore_target)
    move, build = result
    if move == Direction.CENTRE and build is None:
        state.explore_target = None
        return None
    ct.draw_indicator_dot(state.explore_target, 0, 0, 255)
    return result


# -- Expanding ring (ECON) --


def _advance_frontier(state: State) -> None:
    cx, cy = state.my_core.x, state.my_core.y
    limit = max(state.w, state.h)
    while state.explore_radius < limit:
        r = state.explore_radius + 1
        if _ring_has_unseen(state, cx, cy, r):
            break
        state.explore_radius = r


def _ring_has_unseen(state: State, cx: int, cy: int, r: int) -> bool:
    x0, x1 = max(0, cx - r), min(state.w - 1, cx + r)
    y0, y1 = max(0, cy - r), min(state.h - 1, cy + r)
    for x in range(x0, x1 + 1):
        if state.is_unseen(x, y0):
            return True
        if state.is_unseen(x, y1):
            return True
    for y in range(y0 + 1, y1):
        if state.is_unseen(x0, y):
            return True
        if state.is_unseen(x1, y):
            return True
    return False


def _pick_ring_target(state: State) -> Position | None:
    cx, cy = state.my_core.x, state.my_core.y
    pos = state.pos
    r = state.explore_radius + 5
    x0, x1 = max(0, cx - r), min(state.w - 1, cx + r)
    y0, y1 = max(0, cy - r), min(state.h - 1, cy + r)
    candidates: list[Position] = []
    for x in range(x0, x1 + 1):
        if state.is_unseen(x, y0):
            candidates.append(Position(x, y0))
        if state.is_unseen(x, y1):
            candidates.append(Position(x, y1))
    for y in range(y0 + 1, y1):
        if state.is_unseen(x0, y):
            candidates.append(Position(x0, y))
        if state.is_unseen(x1, y):
            candidates.append(Position(x1, y))
    if not candidates:
        return None
    rng = Random(hash((pos.x, pos.y, state.explore_radius)))
    return candidates[rng.randrange(len(candidates))]


# -- Biased explore (ATTACK) --


def _pick_biased_target(state: State) -> Position | None:
    w = state.w
    h = state.h
    pos = state.pos
    max_dim = max(w, h)

    if state.en_core_pos is not None:
        bias_x, bias_y = state.en_core_pos.x, state.en_core_pos.y
    else:
        bias_x, bias_y = w - 1 - state.my_core.x, h - 1 - state.my_core.y

    best: Position | None = None
    best_score = -1_000_000

    for y in range(0, h, 3):
        for x in range(0, w, 3):
            if not state.is_unseen(x, y):
                continue
            walk_dist = max(abs(pos.x - x), abs(pos.y - y))
            bias_dist = max(abs(bias_x - x), abs(bias_y - y))
            closeness = max_dim - bias_dist
            score = -walk_dist + closeness * 0.5
            if score > best_score:
                best_score = score
                best = Position(x, y)

    return best
