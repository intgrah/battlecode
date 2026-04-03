"""Expanding-ring exploration.

Maintains a Chebyshev-distance ring centered on the core. The ring
advances (by 3) when all perimeter tiles have been seen. The builder
navigates to a random unseen tile on the ring's frontier.

Commitment: once a target is picked, it persists until the tile is seen
(builder walks close enough for it to enter vision). This prevents
oscillation between candidates.
"""

from random import Random

from cambc import Controller, Position

from .action import Turn
from .helpers import move_toward_with_road
from .state import State


def explore(
    state: State,
    ct: Controller,
) -> Turn | None:
    _advance_frontier(state)
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x,
        state.explore_target.y,
    ):
        state.explore_target = None
    if state.explore_target is None:
        state.explore_target = _pick_frontier_target(state)
    if state.explore_target is None:
        return None
    result = move_toward_with_road(state, ct, state.explore_target)
    if result is None:
        return None
    ct.draw_indicator_dot(state.explore_target, 0, 0, 255)
    return result


def _advance_frontier(state: State) -> None:
    cx, cy = state.my_core
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


def _pick_frontier_target(state: State) -> Position | None:
    cx, cy = state.my_core
    pos = state.pos
    r = state.explore_radius + 3
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
