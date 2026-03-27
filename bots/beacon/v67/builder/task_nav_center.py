"""Expanding-ring exploration centered on the map center.

Same logic as task_explore but centered on (w//2, h//2) instead of the
core. The bot spirals outward from center, building roads as it goes.
"""

from random import Random

from cambc import Controller, Direction, Position

from .build import Action
from .helpers import move_toward_with_road
from .state import State


def nav_center(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    cx, cy = state.w // 2, state.h // 2
    _advance_frontier(state, cx, cy)
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x,
        state.explore_target.y,
    ):
        state.explore_target = None
    if state.explore_target is None:
        state.explore_target = _pick_frontier_target(state, cx, cy)
    if state.explore_target is None:
        return None
    move, build = move_toward_with_road(state, ct, state.explore_target)
    state.debug_target = (state.explore_target, 255, 0, 255)
    return move, build


def _advance_frontier(state: State, cx: int, cy: int) -> None:
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


def _pick_frontier_target(state: State, cx: int, cy: int) -> Position | None:
    pos = state.pos
    r = state.explore_radius + 3
    x0, x1 = max(0, cx - r), min(state.w - 1, cx + r)
    y0, y1 = max(0, cy - r), min(state.h - 1, cy + r)
    candidates: list[tuple[int, int]] = []
    for x in range(x0, x1 + 1):
        if state.is_unseen(x, y0):
            candidates.append((x, y0))
        if state.is_unseen(x, y1):
            candidates.append((x, y1))
    for y in range(y0 + 1, y1):
        if state.is_unseen(x0, y):
            candidates.append((x0, y))
        if state.is_unseen(x1, y):
            candidates.append((x1, y))
    if not candidates:
        return None
    rng = Random(hash((pos.x, pos.y, state.explore_radius)))
    c = candidates[rng.randrange(len(candidates))]
    return Position(c[0], c[1])
