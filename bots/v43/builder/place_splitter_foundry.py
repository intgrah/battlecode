"""Replace a conveyor adjacent to a foundry with a splitter.

Method 2 of RAx refining (splitter tech). After place_foundry_mixed_conv
has placed a foundry next to a mixed-flow conveyor, this task replaces
that conveyor with a splitter. The splitter diverts a fraction of the
mixed flow to the foundry while forwarding the rest along the original
direction.

The splitter preserves the original direction of the conveyor it replaces,
ensuring downstream flow continues uninterrupted.
"""

from cambc import Controller, Direction, EntityType, Position

from .base import BuilderBase
from .build import Action, PlaceSplitter


class PlaceSplitterFoundryMixin(BuilderBase):
    def _place_splitter_foundry(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        w = self.state.w
        for fi in self.state.my_foundries:
            fx, fy = fi % w, fi // w
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = fx + dx, fy + dy
                if not self.state.in_bounds(nx, ny):
                    continue
                ni = self.state.idx(nx, ny)
                ent = self.state.entity[ni]
                if ent is None:
                    continue
                if ent[0] not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                    continue
                if ent[1] != self.state.my_team:
                    continue
                d = self.state.direction[ni]
                if d is None:
                    continue
                target = Position(nx, ny)

                if pos.distance_squared(target) <= 2 and pos != target:
                    self._debug_target = (target, 255, 200, 0)
                    return Direction.CENTRE, PlaceSplitter(target, d)

                adj = self._cardinal_adjacent(pos, target)
                if adj is None:
                    continue
                move, build = self._move_toward_with_road(ct, pos, adj)
                if move != Direction.CENTRE and build is None:
                    new_pos = pos.add(move)
                    if new_pos.distance_squared(target) <= 2 and new_pos != target:
                        build = PlaceSplitter(target, d)
                self._debug_target = (target, 255, 200, 0)
                return move, build
        return None
