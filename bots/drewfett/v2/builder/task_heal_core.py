"""Heal the core when damaged."""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import Action, Heal
from cambc import Controller, Direction, GameConstants

from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State


def heal_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    if state.my_core_hp >= GameConstants.CORE_MAX_HP:
        return None

    core = state.my_core

    # Already in range -- heal
    if state.pos.distance_squared(
        core
    ) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(core):
        return Direction.CENTRE, Heal(core)

    # Walk toward core
    result = move_toward_with_road(state, ct, core)
    move, build = result
    if move == Direction.CENTRE and build is None:
        return None
    ct.draw_indicator_line(state.pos, core, 255, 0, 0)
    return result
