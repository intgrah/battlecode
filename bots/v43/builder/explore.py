from random import Random

from cambc import Controller, Direction, Position

from .base import BuilderBase
from .build import Action


class ExploreMixin(BuilderBase):
    """Expanding-ring exploration.

    Maintains a Chebyshev-distance ring centered on the core. The ring
    advances when all perimeter tiles have been seen. The builder navigates
    to a random unseen tile on the ring's frontier.

    Commitment: once a target is picked, it persists until the tile is seen
    (builder walks close enough for it to enter vision). This prevents
    oscillation between candidates.
    """

    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self._explore_target: Position | None = None
        self._explore_radius = 0

    def _explore(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Action | None] | None:
        self._advance_frontier()
        if self._explore_target is not None and not self.belief.is_unseen(
            self._explore_target.x,
            self._explore_target.y,
        ):
            self._explore_target = None
        if self._explore_target is None:
            self._explore_target = self._pick_frontier_target(pos)
        if self._explore_target is None:
            return None
        move, build = self._move_toward_with_road(ct, pos, self._explore_target)
        self._debug_target = (self._explore_target, 0, 0, 255)
        return move, build

    def _advance_frontier(self) -> None:
        cx, cy = self.belief.my_core
        limit = max(self.w, self.h)
        while self._explore_radius < limit:
            r = self._explore_radius + 1
            if self._ring_has_unseen(cx, cy, r):
                break
            self._explore_radius = r

    def _ring_has_unseen(self, cx: int, cy: int, r: int) -> bool:
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        for x in range(x0, x1 + 1):
            if self.belief.is_unseen(x, y0):
                return True
            if self.belief.is_unseen(x, y1):
                return True
        for y in range(y0 + 1, y1):
            if self.belief.is_unseen(x0, y):
                return True
            if self.belief.is_unseen(x1, y):
                return True
        return False

    def _pick_frontier_target(self, pos: Position) -> Position | None:
        cx, cy = self.belief.my_core
        r = self._explore_radius + 3
        x0, x1 = max(0, cx - r), min(self.belief.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.belief.h - 1, cy + r)
        candidates: list[tuple[int, int]] = []
        for x in range(x0, x1 + 1):
            if self.belief.is_unseen(x, y0):
                candidates.append((x, y0))
            if self.belief.is_unseen(x, y1):
                candidates.append((x, y1))
        for y in range(y0 + 1, y1):
            if self.belief.is_unseen(x0, y):
                candidates.append((x0, y))
            if self.belief.is_unseen(x1, y):
                candidates.append((x1, y))
        if not candidates:
            return None
        rng = Random(hash((pos.x, pos.y, self._explore_radius)))
        c = candidates[rng.randrange(len(candidates))]
        return Position(c[0], c[1])
