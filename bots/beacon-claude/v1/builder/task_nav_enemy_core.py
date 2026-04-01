"""Navigate toward the enemy core.

Succeeds only when the enemy core position is known (from symmetry or
direct observation) and A* finds a path. Used for rush/cheese strategies
where builders need to reach enemy territory to place turrets or disrupt
infrastructure.
"""

from cambc import Controller, Direction, Position

from .build import Action
from .helpers import move_toward_with_road
from .state import State


def nav_enemy_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    en_core = state.en_core
    if en_core is None:
        return None
    target = Position(en_core[0], en_core[1])
    move, build = move_toward_with_road(state, ct, target)
    if move == Direction.CENTRE and build is None:
        return None
    state.debug_target = (target, 255, 0, 0)
    return move, build
