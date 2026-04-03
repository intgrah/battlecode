"""Heal the core."""

from action import ActionOnly, Heal, Turn
from cambc import Controller, GameConstants, Position

from .helpers import move_toward_with_road
from .state import State


def heal_core(
    state: State,
    ct: Controller,
) -> Turn | None:
    if state.my_core_hp >= GameConstants.CORE_MAX_HP:
        return None

    core = Position(state.my_core[0], state.my_core[1])

    if state.pos.distance_squared(
        core,
    ) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(
        core,
    ):
        print(f"    heal_core: hp={state.my_core_hp}")
        return ActionOnly(Heal(core))

    result = move_toward_with_road(state, ct, core)
    if result is None:
        return None
    print(f"    heal_core: nav to ({core.x},{core.y}) hp={state.my_core_hp}")
    ct.draw_indicator_line(state.pos, core, 255, 0, 0)
    return result
