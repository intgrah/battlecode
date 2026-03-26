"""Raid enemy transport by walking onto it and attacking.

The builder navigates to the highest-flow enemy transport tile, walks onto
it, and uses the attack action (2 Ti for 2 damage). Targets conveyors,
bridges, and splitters. Self-destruct damage was removed in the balance
patch — only the attack action works now.
"""

from cambc import Controller, Direction, EntityType, Position

from .base import BuilderBase
from .build import Action, SelfDestruct

_RAIDABLE = frozenset((EntityType.CONVEYOR, EntityType.BRIDGE, EntityType.SPLITTER))


class RaidMixin(BuilderBase):
    def _raid(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        best_tile = None
        best_flow = 0.0
        w = self.state.w
        for i in self.state.en_transport:
            if self.state.en_flow.total[i] <= 0:
                continue
            ent = self.state.entity[i]
            if ent is None or ent[0] not in _RAIDABLE:
                continue
            if i in self.state.unit_tiles:
                continue
            if self.state.en_flow.total[i] > best_flow:
                best_flow = self.state.en_flow.total[i]
                best_tile = (i % w, i // w)
        if best_tile is None:
            return None
        target = Position(best_tile[0], best_tile[1])
        if pos == target:
            return Direction.CENTRE, SelfDestruct(pos)
        move = self._move_toward(ct, pos, target)
        self._debug_target = (target, 255, 0, 255)
        return move, None
