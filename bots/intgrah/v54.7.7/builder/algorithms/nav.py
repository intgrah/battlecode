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

from typing import TYPE_CHECKING

from builder.algorithms.bug2_planner import _build_mline_seq, bug2_plan_iter
from builder.algorithms.dp_step import dp_step
from cambc import Position
from util.constants import INF, MAX_N, MAX_WIDTH
from util.debug import debug as log
from util.visualiser import DumpScalar

if TYPE_CHECKING:
    from collections.abc import Iterator

    from builder import Builder


_PLAN_BUDGET: int = 25


class BugNav:
    """Per-builder navigation state. One instance lives on each builder."""

    __slots__ = (
        "_active_goal",
        "_active_start",
        "_committed",
        "_gen",
        "_gen_done",
        "_path_idx",
        "_unreachable",
    )

    def __init__(self) -> None:
        self._active_goal: Position | None = None
        self._active_start: Position | None = None
        self._gen: Iterator[int] | None = None
        self._gen_done: bool = False
        self._path_idx: list[int] = [-1] * MAX_N
        self._unreachable: bool = False
        self._committed: list[int] = []
        """Cell indices the planner has committed to the path so far,
        in the order they were laid down. Used by `_draw_plan` to draw
        the full plan (not just the visible slice). Reset on replan."""

    def step(
        self: BugNav,
        bot: Builder,
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

        # Run the plan-then-dp pipeline at most twice. First attempt
        # uses the cached plan (if any). If dp_step says the plan is
        # unactionable from here (no tile within the 69-cell window has
        # both path_idx > current AND is reachable), force a replan and
        # try once more.
        for attempt in range(2):
            force_replan = attempt == 1
            replan = (
                force_replan
                or goal != self._active_goal
                or not self._any_path_tile_visible(bot)
            )

            if replan:
                self._active_goal = goal
                self._active_start = pos
                self._path_idx[:] = [-1] * MAX_N
                self._path_idx[si] = 0
                self._unreachable = False
                self._committed = [si]
                self._gen = bug2_plan_iter(
                    bot.cost_grid,
                    bot.w,
                    bot.h,
                    si,
                    gi,
                    self._path_idx,
                )
                self._gen_done = False

            if self._unreachable:
                log(
                    "bugnav.step exit: unreachable attempt={a}",
                    a=DumpScalar(attempt),
                )
                return None

            if not self._gen_done and self._gen is not None:
                for _ in range(_PLAN_BUDGET):
                    try:
                        yielded = next(self._gen)
                    except StopIteration as e:
                        self._gen_done = True
                        if e.value is False:
                            self._unreachable = True
                        break
                    if yielded != -1:
                        self._committed.append(yielded)
                if self._unreachable:
                    log(
                        "bugnav.step exit: planner declared unreachable attempt={a}",
                        a=DumpScalar(attempt),
                    )
                    return None

            # Overlay other-builder positions as INF in cost_grid so dp_step
            # routes around them. Restore after the call.
            cost_grid = bot.cost_grid
            saved: list[tuple[int, int]] = []
            for fb_pos in bot.all_bots:
                if fb_pos == pos:
                    continue
                fi = fb_pos.y * MAX_WIDTH + fb_pos.x
                saved.append((fi, cost_grid[fi]))
                cost_grid[fi] = INF
            nxt = dp_step(
                MAX_WIDTH,
                cost_grid,
                bot.h,
                si,
                self._path_idx,
                self._path_idx[si],
            )
            for fi, prev in saved:
                cost_grid[fi] = prev

            # dp_step returns the chosen next-step tile (one of the 8
            # immediate neighbours) or `si` if no path tile within the
            # 69-cell window is reachable. The returned tile is the
            # *gateway* (first step) toward the deepest path-cell found
            # — it may itself not be on the plan. `nxt == si` is the
            # only signal that the plan is unactionable from here.
            log(
                "bugnav.step dp result: a={a} si={si} nxt={nxt} committed={c}",
                a=DumpScalar(attempt),
                si=DumpScalar(si),
                nxt=DumpScalar(nxt),
                c=DumpScalar(len(self._committed)),
            )
            if nxt == si:
                # First attempt: plan is stale, retry with fresh plan.
                # Second attempt: stale even after replan, give up.
                continue

            return Position(nxt % MAX_WIDTH, nxt // MAX_WIDTH)

        log("bugnav.step exit: both attempts failed")
        return None

    def _any_path_tile_visible(self: BugNav, bot: Builder) -> bool:
        """True iff at least one tile in `nearby_tiles` has a path index
        set (i.e. the cached plan still passes through visible space).
        """
        path_idx = self._path_idx
        for tile in bot.nearby_tiles:
            if path_idx[tile.y * MAX_WIDTH + tile.x] != -1:
                return True
        return False

    @property
    def path_idx_array(self: BugNav) -> list[int]:
        """Raw flat path-index array. Cell value = position-along-path,
        -1 if not on plan. Used by the state dump as an I16Grid."""
        return self._path_idx

    def committed_positions(self: BugNav) -> list[Position]:
        """Cells the planner has committed to the path so far, in order
        (start → goalward). Used by the state dump as a `DumpPath`."""
        return [Position(i % MAX_WIDTH, i // MAX_WIDTH) for i in self._committed]

    @property
    def active_goal(self: BugNav) -> Position | None:
        return self._active_goal

    @property
    def gen_done(self: BugNav) -> bool:
        """True iff the planner generator finished (StopIteration or
        Unreachable). When False, the planner is still suspended and
        will resume next turn."""
        return self._gen_done

    @property
    def unreachable(self: BugNav) -> bool:
        """True iff the planner concluded the goal is unreachable. When
        this is True, `step()` returns None unconditionally until the
        goal changes."""
        return self._unreachable

    def mline(self: BugNav) -> list[Position]:
        """Bresenham m-line from the active plan's start to the goal.
        Empty if there's no active plan. Used by the state dump."""
        if self._active_start is None or self._active_goal is None:
            return []
        s = self._active_start
        g = self._active_goal
        return [Position(x, y) for x, y in _build_mline_seq(s.x, s.y, g.x, g.y)]
