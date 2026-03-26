from cambc import Controller, Direction, Position

from .base import BuilderBase
from .build import Action


class NavEnemyCoreMixin(BuilderBase):
    """Navigate toward the enemy core.

    Succeeds only when the enemy core position is known (from symmetry or
    direct observation) and A* finds a path. Used for rush/cheese strategies
    where builders need to reach enemy territory to place turrets or disrupt
    infrastructure.
    """

    def _nav_enemy_core(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        en_core = self.state.en_core
        if en_core is None:
            return None
        target = Position(en_core[0], en_core[1])
        move, build = self._move_toward_with_road(ct, pos, target)
        if move == Direction.CENTRE and build is None:
            return None
        self._debug_target = (target, 255, 0, 0)
        return move, build
