"""Exploration with role-aware strategies.

ECON (role 0): Expanding ring from core — systematic, finds all nearby ore.
ATTACK (role 1): Bias toward enemy core — scout enemy half.
DEFENSE (role 2): Bias toward our core — patrol nearby.

Commitment: once a target is picked, it persists until the tile is seen.
"""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .action import Action
    from .state import State


def explore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    import time as _time

    _t = _time.perf_counter
    # Clear target if seen
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x,
        state.explore_target.y,
    ):
        state.explore_target = None

    _t0 = _t()
    if state.explore_target is None:
        if state.role == 0:  # ECON: expanding ring
            _advance_frontier(state)
            state.explore_target = _pick_ring_target(state)
        else:
            state.explore_target = _pick_biased_target(state)
    _t1 = _t()

    if state.explore_target is None:
        return None

    result = move_toward_with_road(state, ct, state.explore_target)
    _t2 = _t()
    pick_us = int((_t1 - _t0) * 1e6)
    nav_us = int((_t2 - _t1) * 1e6)
    if pick_us + nav_us > 500:
        import sys

        print(f"  explore: pick={pick_us} nav={nav_us}", file=sys.stderr)
    if result is None:
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
        unseen_frac = _ring_unseen_frac(state, cx, cy, r)
        if unseen_frac > 0.2:  # advance if <=80% seen
            break
        state.explore_radius = r


def _ring_unseen_frac(state: State, cx: int, cy: int, r: int) -> float:
    x0 = max(0, cx - r)
    x1 = min(state.w - 1, cx + r)
    y0 = max(0, cy - r)
    y1 = min(state.h - 1, cy + r)
    total = 0
    unseen = 0
    for x in range(x0, x1 + 1):
        total += 1
        if state.is_unseen(x, y0):
            unseen += 1
        total += 1
        if state.is_unseen(x, y1):
            unseen += 1
    for y in range(y0 + 1, y1):
        total += 1
        if state.is_unseen(x0, y):
            unseen += 1
        total += 1
        if state.is_unseen(x1, y):
            unseen += 1
    return unseen / max(total, 1)


def _pick_ring_target(state: State) -> Position | None:
    cx, cy = state.my_core.x, state.my_core.y
    r = state.explore_radius + 5
    x0 = max(0, cx - r)
    x1 = min(state.w - 1, cx + r)
    y0 = max(0, cy - r)
    y1 = min(state.h - 1, cy + r)
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
    # Pick random from candidates, seeded by position + radius for determinism
    pos = state.pos
    rng = Random(hash((pos.x, pos.y, state.explore_radius)))
    return candidates[rng.randrange(len(candidates))]


# -- Biased explore (ATTACK / DEFENSE) --


def _pick_biased_target(state: State) -> Position | None:
    w = state.w
    h = state.h
    pos = state.pos
    max_dim = max(w, h)

    if state.role == 2:  # DEFENSE: bias toward our core
        bias_x, bias_y = state.my_core.x, state.my_core.y
    elif state.en_core_pos is not None:
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
