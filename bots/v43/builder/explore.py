from random import Random

from cambc import Controller, Direction, Position
from marker import TaskClaim, TaskKind

from .base import BuilderBase
from .build import Build


class ExploreMixin(BuilderBase):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self._explore_target: Position | None = None
        self._explore_radius = 0

    def _explore(
        self,
        ct: Controller,
        pos: Position,
    ) -> tuple[Direction, Build | None] | None:
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
        w = self.belief.w
        ti = self._explore_target
        rnd = ct.get_current_round()
        self._claim = TaskClaim(TaskKind.EXPLORE, ti.y * w + ti.x, rnd)
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
        r = self._explore_radius + 1
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
        # Pick the closest candidate to this builder (not random) for efficiency.
        # Use builder position hash to break ties and spread builders.
        rng = Random(hash((pos.x, pos.y, self._explore_radius)))
        rng.shuffle(candidates)
        candidates.sort(key=lambda c: (pos.x - c[0]) ** 2 + (pos.y - c[1]) ** 2)
        # Skip candidates claimed by other builders.
        w = self.belief.w
        for c in candidates:
            ci = c[1] * w + c[0]
            if not self._is_claimed(ci, TaskKind.EXPLORE):
                return Position(c[0], c[1])
        # If all claimed, just take closest.
        c = candidates[0]
        return Position(c[0], c[1])
