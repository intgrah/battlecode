"""Heal the core."""

from cambc import Controller, Direction, GameConstants, Position

from .action import Action, Heal
from .helpers import move_toward_with_road
from .state import State


def heal_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    if state.my_core_hp >= GameConstants.CORE_MAX_HP:
        return None

    core = Position(state.my_core[0], state.my_core[1])

    if state.pos.distance_squared(
        core,
    ) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(
        core,
    ):
        return Direction.CENTRE, Heal(core)

    move, build = move_toward_with_road(state, ct, core)
    ct.draw_indicator_line(state.pos, core, 255, 0, 0)
    return move, build
