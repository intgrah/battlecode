"""
Translation of `bots/intgrah/v54.7.9/builder/algorithms/nav.py`.

Movement navigation: bug2-bounded planner + `dp_step` path-follower.

Replaces A*/BFS for movement. Plan-incrementally-walk reactive style:

- The `BugNav` state holds (goal, `path_idx`, planner, `gen_done`).
- Each turn, when the bot wants to move toward a goal:
  - If `goal` differs from cached, reset state and start a new plan.
  - Else if no path-tile is currently visible, the cached plan is stale
    (we drifted off-plan); reset and start a new plan.
  - Else: drain BUDGET planner steps to extend the plan.
- Then `dp_step(cost, pos, path_idx)` picks the next move: the visible
  cell with maximum `path_idx` (closest goalward, with cost-aware tiebreak).
"""

from __future__ import annotations

from typing import Final

from cambc import Position
from builder.algorithms.bug2_planner import Bug2Planner, build_mline_seq
from builder.algorithms.dp_step import dp_step
from util.constants import INF, MAX_N, MAX_WIDTH

PLAN_BUDGET: Final[int] = 25


class NavCtx:
    """
    Subset of `Builder` state read by nav. Phase G6's `Builder` will populate
    this each turn from its own fields and pass `&mut` to `step`.
    """

    my_pos: Position
    cost_grid: list[int]
    w: int
    h: int
    nearby_tiles: list[Position]
    all_bots: dict[Position, int]

    def __init__(
        self,
        my_pos: Position,
        cost_grid: list[int],
        w: int,
        h: int,
        nearby_tiles: list[Position],
        all_bots: dict[Position, int],
    ):
        self.my_pos = my_pos
        self.cost_grid = cost_grid
        self.w = w
        self.h = h
        self.nearby_tiles = nearby_tiles
        self.all_bots = all_bots


class BugNav:
    """Per-builder navigation state. One instance lives on each builder."""

    active_goal: Position | None
    active_start: Position | None
    planner: Bug2Planner | None
    gen_done: bool
    path_idx_storage: list[int]
    unreachable: bool
    committed: list[int]

    def __init__(self):
        self.active_goal = None
        self.active_start = None
        self.planner = None
        self.gen_done = False
        self.path_idx_storage = [-1] * MAX_N
        self.unreachable = False
        self.committed = []

    @staticmethod
    def default():
        return BugNav()

    def path_idx(self):
        """
        Read-only access to the current `path_idx` array (whether owned by the
        planner or by storage).
        """
        p = self.planner
        if p is not None:
            return p.path_idx()
        else:
            return self.path_idx_storage

    def step(self, ctx, goal):
        """
        Return the next position to move toward `goal`, or `None` if no
        progress can be made (no path or already at goal).

        Replans iff:
          - goal changed since last call, OR
          - the current plan has no tile visible to the bot (drifted off).
        """
        pos = ctx.my_pos
        if pos == goal:
            return None
        stride = int(50)
        si = pos.y * stride + pos.x
        gi = goal.y * stride + goal.x
        for attempt in range(0, 2):
            force_replan = attempt == 1
            replan = (
                force_replan
                or goal != self.active_goal
                or not self.any_path_tile_visible(ctx.nearby_tiles)
            )
            if replan:
                planner = ((__t0 := self.planner), setattr(self, "planner", None))[0]
                if planner is not None:
                    self.path_idx_storage = planner._path_idx
                self.active_goal = goal
                self.active_start = pos
                self.path_idx_storage[:] = [-1] * len(self.path_idx_storage)
                self.path_idx_storage[int(si)] = 0
                self.unreachable = False
                self.committed = [si]
                path_idx = (
                    (__t1 := self.path_idx_storage),
                    setattr(self, "path_idx_storage", []),
                )[0]
                self.planner = Bug2Planner(
                    ctx.cost_grid, ctx.w, ctx.h, si, gi, path_idx
                )
                self.gen_done = False
            if self.unreachable:
                return None
            if not self.gen_done and (self.planner is not None):
                for _ in range(0, 25):
                    planner = self.planner
                    match planner.step(ctx.cost_grid):
                        case None:
                            yielded = planner.last_yielded
                            if yielded != -1:
                                self.committed.append(yielded)
                        case True:
                            self.gen_done = True
                            self.path_idx_storage = (
                                (__t2 := self.planner),
                                setattr(self, "planner", None),
                            )[0]._path_idx
                            break
                        case False:
                            self.gen_done = True
                            self.unreachable = True
                            self.path_idx_storage = (
                                (__t3 := self.planner),
                                setattr(self, "planner", None),
                            )[0]._path_idx
                            break
                if self.unreachable:
                    return None
            saved: list[tuple[int, int]] = []
            for fb_pos in ctx.all_bots.keys():
                if fb_pos == pos:
                    continue
                fi = int(fb_pos.y * stride + fb_pos.x)
                saved.append((fi, ctx.cost_grid[fi]))
                ctx.cost_grid[fi] = 1000000
            path_idx_ref: list[int] = (
                p.path_idx()
                if ((p := self.planner) is not None)
                else self.path_idx_storage
            )
            cur_min = path_idx_ref[int(si)]
            nxt = dp_step(int(50), ctx.cost_grid, ctx.h, si, path_idx_ref, cur_min)
            for fi, prev in saved:
                ctx.cost_grid[fi] = prev
            if nxt == si:
                continue
            return Position(x=nxt % stride, y=nxt // stride)
        return None

    def any_path_tile_visible(self, nearby):
        stride = int(50)
        path_idx = self.path_idx()
        for tile in nearby:
            if path_idx[int(tile.y * stride + tile.x)] != -1:
                return True
        return False

    def path_idx_array(self):
        """
        Raw flat path-index array. Cell value = position-along-path,
        `-1` if not on plan. Used by the state dump as an `I16Grid`.
        """
        return self.path_idx()

    def committed_positions(self):
        """
        Cells the planner has committed to the path so far, in order
        (start → goalward). Used by the state dump as a `DumpPath`.
        """
        stride = int(50)
        return list((Position(x=i % stride, y=i // stride) for i in self.committed))

    def mline(self):
        """
        Bresenham m-line from the active plan's start to the goal. Empty
        if there's no active plan. Used by the state dump.
        """
        s = self.active_start
        g = self.active_goal
        if s is None or g is None:
            return []
        return list(
            (Position(x=t[0], y=t[1]) for t in build_mline_seq(s.x, s.y, g.x, g.y))
        )
