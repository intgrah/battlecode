"""Expanding-ring exploration with explore claims.

Maintains a Chebyshev-distance ring centered on the core. The ring
advances (by 3) when all perimeter tiles have been seen. The builder
navigates to the unseen frontier tile that is furthest from any other
builder's claimed explore target, avoiding duplicated work.

Commitment: once a target is picked, it persists until the tile is seen.
The builder writes a MarkerExploreClaim so other builders avoid the area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position
from marker import MarkerExploreClaim

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .action import Action
    from .state import State

_CLAIM_RADIUS_SQ = 25  # tiles within 5 Chebyshev of a claimed target are "taken"


def explore(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
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

    # Write explore claim so other builders avoid this area
    rnd = ct.get_current_round()
    ti = state.explore_target.y * state.w + state.explore_target.x
    state.pending_explore_claim = MarkerExploreClaim(tile_index=ti, turn=rnd)

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
    w = state.w
    r = state.explore_radius + 3
    x0, x1 = max(0, cx - r), min(w - 1, cx + r)
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

    # Score each candidate: prefer tiles far from other builders' explore claims
    claimed = state.explore_claims
    pos = state.pos

    def _score(p: Position) -> int:
        p.y * w + p.x
        # Min Chebyshev distance to any claimed explore target
        min_claim_dist = 999
        for ci in claimed:
            cx2, cy2 = ci % w, ci // w
            d = max(abs(p.x - cx2), abs(p.y - cy2))
            min_claim_dist = min(min_claim_dist, d)
        # Walk distance (lower is better)
        walk = max(abs(pos.x - p.x), abs(pos.y - p.y))
        # Maximize distance from claims, minimize walk distance
        # Negate claim distance so sorting ascending picks best
        return walk - min_claim_dist * 2

    candidates.sort(key=_score)
    return candidates[0]
