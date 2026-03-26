from cambc import Controller, Direction, Position

from .build import Action, Heal
from .helpers import move_toward_with_road
from .state import State


def heal_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    if state.my_core_hp >= state.my_core_max_hp:
        return None

    core = Position(state.my_core[0], state.my_core[1])
    pos = state.pos

    if pos.distance_squared(core) <= 2 and ct.can_heal(core):
        return Direction.CENTRE, Heal(core)

    move, build = move_toward_with_road(state, ct, core)
    state.debug_target = (core, 255, 0, 0)
    return move, build
