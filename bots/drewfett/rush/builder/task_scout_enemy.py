"""Scout near enemy core to find ore and harvesters for the siege.

Picks unseen tiles near the enemy core and walks toward them.
Only runs for builders on the enemy half. Discovers ore/harvesters
that RUSH can then tap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .action import Action
    from .state import State


def _move_or_none(
    state: State, ct: Controller, target: Position,
) -> tuple[Direction, Action | None] | None:
    result = move_toward_with_road(state, ct, target)
    move, build = result
    if move == Direction.CENTRE and build is None:
        return None
    return result


def scout_enemy(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    en_core = state.en_core_pos
    if en_core is None:
        return None

    pos = state.pos

    # Builders on our half: only scout if we have Ti flowing to core
    on_enemy_half = pos.distance_squared(en_core) <= pos.distance_squared(state.my_core)
    if not on_enemy_half:
        has_income = any(state.flow.ti[i] > 0 for i in state.my_core_tiles)
        if not has_income:
            return None

    # Committed target — persist until seen
    if state.explore_target is not None and not state.is_unseen(
        state.explore_target.x,
        state.explore_target.y,
    ):
        state.explore_target = None

    if state.explore_target is None:
        state.explore_target = _pick_target(state, en_core)
    if state.explore_target is None:
        # Nothing unseen near enemy — just walk toward core
        return _move_or_none(state, ct, en_core)

    ct.draw_indicator_dot(state.explore_target, 0, 255, 255)  # cyan dot
    return _move_or_none(state, ct, state.explore_target)


def _pick_target(state: State, en_core: Position) -> Position | None:
    """Pick nearest unseen tile to the enemy core."""
    w = state.w
    h = state.h
    best: Position | None = None
    best_dist = 1_000_000

    # Sample tiles near enemy core
    for dy in range(-15, 16, 2):
        for dx in range(-15, 16, 2):
            x, y = en_core.x + dx, en_core.y + dy
            if not (0 <= x < w and 0 <= y < h):
                continue
            if not state.is_unseen(x, y):
                continue
            # Score by distance from builder (walk cost)
            walk = (state.pos.x - x) ** 2 + (state.pos.y - y) ** 2
            # Prefer tiles closer to enemy core
            core_dist = dx * dx + dy * dy
            dist = walk + core_dist
            if dist < best_dist:
                best_dist = dist
                best = Position(x, y)

    return best
