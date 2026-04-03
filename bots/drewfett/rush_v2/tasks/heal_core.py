"""Heal the core when damaged. Highest priority for all roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import Heal
from cambc import GameConstants, Position
from turn import ActionOnly, Turn

from ._helpers import move_toward

if TYPE_CHECKING:
    from cambc import Controller
    from state import State


def run(state: State, ct: Controller) -> Turn | None:
    if state.my_core_hp >= GameConstants.CORE_MAX_HP:
        return None

    # Find any core tile to heal (pick the first one within action range)
    core = state.my_core
    core_tiles: list[Position] = [
        Position(core.x + dx, core.y + dy)
        for dx in range(-1, 2)
        for dy in range(-1, 2)
        if state.in_bounds(core.x + dx, core.y + dy)
    ]

    # If adjacent to any core tile (action radius sq 2), heal it
    for tile in core_tiles:
        if state.pos.distance_squared(
            tile
        ) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(tile):
            return ActionOnly(Heal(tile))

    # Not adjacent -- move toward core centre
    return move_toward(state, ct, core)
