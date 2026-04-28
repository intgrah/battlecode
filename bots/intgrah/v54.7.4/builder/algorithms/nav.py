"""Movement navigation: bug2-bounded planner + dp_step path-follower.

Replaces A*/BFS for movement. Plan-incrementally-walk reactive style:

- The BugNav state holds (goal, path_idx, generator, gen_done).
- Each turn, when the bot wants to move toward a goal:
  - If `goal` differs from cached, reset state and start a new plan.
  - Else if no path-tile is currently visible, the cached plan is stale
    (we drifted off-plan); reset and start a new plan.
  - Else: drain BUDGET generator iterations to extend the plan.
- Then `dp_step(cost, pos, path_idx)` picks the next move: the visible
  cell with maximum `path_idx` (closest goalward, with cost-aware tiebreak).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from cambc import Controller, Position
from util.constants import MAX_N, MAX_WIDTH
from util.debug import line

from builder.algorithms.bug2_planner import bug2_plan_iter
from builder.algorithms.dp_step import dp_step

if TYPE_CHECKING:
    from builder import Builder


_PLAN_BUDGET: int = 25


class BugNav:
    """Per-builder navigation state. One instance lives on each builder."""

    __slots__ = ("_active_goal", "_gen", "_gen_done", "_path_idx")

    def __init__(self) -> None:
        self._active_goal: Position | None = None
        self._gen: Iterator[None] | None = None
        self._gen_done: bool = False
        self._path_idx: list[int] = [-1] * MAX_N

    def step(
        self: BugNav,
        bot: Builder,
        ct: Controller,
        goal: Position,
    ) -> Position | None:
        """Return the next position to move toward `goal`, or None if no
        progress can be made (no path or already at goal).

        Replans iff:
          - goal changed since last call, OR
          - the current plan has no tile visible to the bot (drifted off).

        Draws indicators for visible plan tiles (green segments) and the
        dp_step shortcut from bot to chosen next-tile (bright cyan).
        """
        pos = bot.my_pos
        if pos == goal:
            return None

        si = pos.y * MAX_WIDTH + pos.x
        gi = goal.y * MAX_WIDTH + goal.x

        replan = False
        if goal != self._active_goal:
            replan = True
        elif not self._any_path_tile_visible(bot):
            replan = True

        if replan:
            self._active_goal = goal
            self._path_idx[:] = [-1] * MAX_N
            self._path_idx[si] = 0
            self._gen = bug2_plan_iter(
                bot.cost_grid, bot.w, bot.h, si, gi, self._path_idx,
            )
            self._gen_done = False

        if not self._gen_done and self._gen is not None:
            for _ in range(_PLAN_BUDGET):
                try:
                    next(self._gen)
                except StopIteration:
                    self._gen_done = True
                    break

        self._draw_plan(ct, bot)

        nxt = dp_step(MAX_WIDTH, bot.cost_grid, bot.h, si, self._path_idx)
        if nxt == si:
            return None
        next_pos = Position(nxt % MAX_WIDTH, nxt // MAX_WIDTH)
        line(ct, pos, next_pos, 0, 255, 255)
        return next_pos

    def _draw_plan(self: BugNav, ct: Controller, bot: Builder) -> None:
        """Draw the planned path as connected segments along visible
        path-tiles in path_idx order. Green, dim."""
        path_idx = self._path_idx
        ordered: list[tuple[int, Position]] = []
        for tile in bot.nearby_tiles:
            i = tile.y * MAX_WIDTH + tile.x
            pi = path_idx[i]
            if pi != -1:
                ordered.append((pi, tile))
        if len(ordered) < 2:
            return
        ordered.sort()
        prev_idx, prev_pos = ordered[0]
        for cur_idx, cur_pos in ordered[1:]:
            if cur_idx == prev_idx + 1:
                line(ct, prev_pos, cur_pos, 0, 160, 0)
            prev_idx, prev_pos = cur_idx, cur_pos

    def _any_path_tile_visible(self: BugNav, bot: Builder) -> bool:
        """True iff at least one tile in `nearby_tiles` has a path index
        set (i.e. the cached plan still passes through visible space).
        """
        path_idx = self._path_idx
        for tile in bot.nearby_tiles:
            if path_idx[tile.y * MAX_WIDTH + tile.x] != -1:
                return True
        return False

    def path_positions(self: BugNav, w: int, h: int) -> list[Position]:
        """Return all tiles on the cached plan, in path-index order.
        Used by the state dump for inspection."""
        path_idx = self._path_idx
        ordered: list[tuple[int, Position]] = []
        for y in range(h):
            base = y * MAX_WIDTH
            for x in range(w):
                pi = path_idx[base + x]
                if pi != -1:
                    ordered.append((pi, Position(x, y)))
        ordered.sort()
        return [p for _, p in ordered]

    @property
    def active_goal(self: BugNav) -> Position | None:
        return self._active_goal

    @property
    def gen_done(self: BugNav) -> bool:
        """True iff the planner generator finished (StopIteration). When
        the path is short and `gen_done` is True, the planner *decided*
        the route is what it returned (likely unreachable from its
        perspective). When False, the planner is still suspended and
        will resume next turn."""
        return self._gen_done
