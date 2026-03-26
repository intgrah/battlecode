"""Patrol friendly infrastructure.

Navigates to the least-recently-seen tile that has friendly infrastructure
(harvesters, transport, foundries, turrets, or core). Keeps the builder's
belief about its own network fresh and detects enemy disruption.
"""

from cambc import Controller, Direction, Position

from .base import BuilderBase
from .build import Action


class PatrolMixin(BuilderBase):
    def _patrol(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        b = self.state
        infra = (
            b.my_harvesters
            | b.my_transport
            | b.my_foundries
            | b.my_turrets
            | b.my_core_tiles
        )
        if not infra:
            return None
        best_tile: int | None = None
        best_freshness = b.age + 1
        for i in infra:
            if b.last_seen[i] < best_freshness:
                best_freshness = b.last_seen[i]
                best_tile = i
        if best_tile is None:
            return None
        x, y = best_tile % b.w, best_tile // b.w
        target = Position(x, y)
        move, build = self._move_toward_with_road(ct, pos, target)
        self._debug_target = (target, 255, 255, 0)
        return move, build
