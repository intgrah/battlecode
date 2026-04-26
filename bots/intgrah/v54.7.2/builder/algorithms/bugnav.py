from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position
from util.constants import INF, MAX_WIDTH
from util.directions import DIR8
from util.metrics import chebyshev

if TYPE_CHECKING:
    from builder import Builder

__all__ = ["bugnav"]


class BugMode(IntEnum):
    MODE_GOAL_SEEK = 0
    MODE_WALL_FOLLOW = 1


class WallFollow:
    def __init__(self, start: Position, goal: Position) -> None:
        self.mode = BugMode.MODE_GOAL_SEEK
        self.start = start
        self.goal = goal
        self.hit_point: Position | None = None
        self.last_pos: Position | None = None
        self.direction = 1
        # Position bugnav last returned. If the bot moved to a tile
        # other than this between calls, it advanced via something else
        # (A*, ct.move, etc.) — wall-follow state is stale.
        self.expected_next: Position | None = None


def _on_baseline(curr: Position, start: Position, goal: Position) -> bool:
    dx_total = goal.x - start.x
    dy_total = goal.y - start.y
    dx_curr = curr.x - start.x
    dy_curr = curr.y - start.y

    cross_product = abs(dy_curr * dx_total - dx_curr * dy_total)

    if cross_product <= max(abs(dx_total), abs(dy_total)) // 2:
        dot_product = dx_curr * dx_total + dy_curr * dy_total
        return dot_product > 0 and chebyshev(curr, goal) < chebyshev(start, goal)
    return False


def bugnav_step(
    self: Builder,
    ct: Controller,
    target: Position,
    blocked: set[Position] | None = None,
) -> Position | None:
    # Reset state if (a) no prior bugnav, (b) the goal changed, or
    # (c) the bot advanced via something other than bugnav since the
    # last call (so `last_pos`/`hit_point`/`start` are stale).
    if (
        self.bug_state is None
        or self.bug_state.goal != target
        or (
            self.bug_state.expected_next is not None
            and self.my_pos != self.bug_state.expected_next
        )
    ):
        self.bug_state = WallFollow(self.my_pos, target)

    bug = self.bug_state
    if blocked is None:
        blocked = set()

    cost_grid = self.cost_grid
    w, h = self.w, self.h

    if self.my_pos == target:
        bug.expected_next = None
        return None

    if bug.last_pos == self.my_pos and bug.mode == BugMode.MODE_GOAL_SEEK:
        bug.mode = BugMode.MODE_WALL_FOLLOW
        bug.hit_point = self.my_pos

    bug.last_pos = self.my_pos

    if bug.mode == BugMode.MODE_GOAL_SEEK:
        dx = target.x - self.my_pos.x
        dy = target.y - self.my_pos.y

        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)

        next_pos = Position(self.my_pos.x + step_x, self.my_pos.y + step_y)

        if (
            0 <= next_pos.x < w
            and 0 <= next_pos.y < h
            and cost_grid[next_pos.y * MAX_WIDTH + next_pos.x] is not INF
            and next_pos not in blocked
        ):
            bug.expected_next = next_pos
            return next_pos
        bug.mode = BugMode.MODE_WALL_FOLLOW
        bug.hit_point = self.my_pos

    if bug.mode == BugMode.MODE_WALL_FOLLOW:
        if (
            bug.hit_point
            and _on_baseline(self.my_pos, bug.start, target)
            and chebyshev(self.my_pos, target) < chebyshev(bug.hit_point, target)
        ):
            bug.mode = BugMode.MODE_GOAL_SEEK
            return bugnav_step(self, ct, target, blocked)

        goal_dx = target.x - self.my_pos.x
        goal_dy = target.y - self.my_pos.y

        def key(d: Direction) -> float:
            # Use the negated dot product with the goal vector so that a
            # direction pointing most toward the goal ranks smallest. Dot
            # product handles angular wraparound correctly — the previous
            # `abs(atan2(dy, dx) - ideal_angle)` scoring could rank NW as
            # "far" from W (7pi/4 due to -3pi/4 vs pi) even though it's
            # adjacent in angle, causing bugnav to choose S/SW instead.
            dx, dy = d.delta()
            return -(dx * goal_dx + dy * goal_dy)

        dirs = DIR8.copy()
        dirs.sort(key=key)

        for d in dirs:
            n = self.my_pos.add(d)
            if not (0 <= n.x < w and 0 <= n.y < h):
                continue

            if cost_grid[n.y * MAX_WIDTH + n.x] is not INF and n not in blocked:
                bug.expected_next = n
                return n

    bug.expected_next = None
    return None


def bugnav(self: Builder, ct: Controller, target: Position) -> Position | None:
    blocked = {pos for pos in self.all_bots if pos != self.my_pos}

    return bugnav_step(self, ct, target, blocked)
