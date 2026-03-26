"""Expanding-ring exploration.

Maintains a Chebyshev-distance ring centered on the core. The ring
advances (by 3) when all perimeter tiles have been seen. The builder
navigates to a random unseen tile on the ring's frontier.

Commitment: once a target is picked, it persists until the tile is seen
(builder walks close enough for it to enter vision). This prevents
oscillation between candidates.
"""

from random import Random

from cambc import Controller, Direction, Position

from .base import BuilderBase
from .build import Action


class ExploreMixin(BuilderBase):
    def _explore(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        s = self.state
        self._advance_frontier()
        if s.explore_target is not None and not s.is_unseen(
            s.explore_target.x,
            s.explore_target.y,
        ):
            s.explore_target = None
        if s.explore_target is None:
            s.explore_target = self._pick_frontier_target(pos)
        if s.explore_target is None:
            return None
        move, build = self._move_toward_with_road(ct, pos, s.explore_target)
        self._debug_target = (s.explore_target, 0, 0, 255)
        return move, build

    def _advance_frontier(self) -> None:
        s = self.state
        cx, cy = s.my_core
        limit = max(self.w, self.h)
        while s.explore_radius < limit:
            r = s.explore_radius + 1
            if self._ring_has_unseen(cx, cy, r):
                break
            s.explore_radius = r

    def _ring_has_unseen(self, cx: int, cy: int, r: int) -> bool:
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        for x in range(x0, x1 + 1):
            if self.state.is_unseen(x, y0):
                return True
            if self.state.is_unseen(x, y1):
                return True
        for y in range(y0 + 1, y1):
            if self.state.is_unseen(x0, y):
                return True
            if self.state.is_unseen(x1, y):
                return True
        return False

    def _pick_frontier_target(self, pos: Position) -> Position | None:
        cx, cy = self.state.my_core
        r = self.state.explore_radius + 3
        x0, x1 = max(0, cx - r), min(self.state.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.state.h - 1, cy + r)
        candidates: list[tuple[int, int]] = []
        for x in range(x0, x1 + 1):
            if self.state.is_unseen(x, y0):
                candidates.append((x, y0))
            if self.state.is_unseen(x, y1):
                candidates.append((x, y1))
        for y in range(y0 + 1, y1):
            if self.state.is_unseen(x0, y):
                candidates.append((x0, y))
            if self.state.is_unseen(x1, y):
                candidates.append((x1, y))
        if not candidates:
            return None
        rng = Random(hash((pos.x, pos.y, self.state.explore_radius)))
        c = candidates[rng.randrange(len(candidates))]
        return Position(c[0], c[1])
