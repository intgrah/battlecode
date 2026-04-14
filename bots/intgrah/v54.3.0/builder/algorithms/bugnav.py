from __future__ import annotations

import math
from enum import IntEnum
from typing import TYPE_CHECKING

from cambc import Controller, Direction, Position
from util import DIR8, INF

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


_bug_state: WallFollow | None = None


def _chebyshev(p1: Position, p2: Position) -> int:
    return max(abs(p1.x - p2.x), abs(p1.y - p2.y))


def _on_baseline(curr: Position, start: Position, goal: Position) -> bool:
    dx_total = goal.x - start.x
    dy_total = goal.y - start.y
    dx_curr = curr.x - start.x
    dy_curr = curr.y - start.y

    cross_product = abs(dy_curr * dx_total - dx_curr * dy_total)

    if cross_product <= max(abs(dx_total), abs(dy_total)) // 2:
        dot_product = dx_curr * dx_total + dy_curr * dy_total
        return dot_product > 0 and _chebyshev(curr, goal) < _chebyshev(start, goal)
    return False


def bugnav_step(
    self: Builder,
    ct: Controller,
    target: Position,
    blocked: set[Position] | None = None,
) -> Position | None:
    global _bug_state
    my_pos = ct.get_position()

    if _bug_state is None or _bug_state.goal != target:
        _bug_state = WallFollow(my_pos, target)

    bug = _bug_state
    if blocked is None:
        blocked = set()

    cost_grid = self.cost_grid
    w, h = self.w, self.h
    pad = self.pad
    pw = self.pad_w

    if my_pos == target:
        return None

    if bug.last_pos == my_pos and bug.mode == BugMode.MODE_GOAL_SEEK:
        bug.mode = BugMode.MODE_WALL_FOLLOW
        bug.hit_point = my_pos

    bug.last_pos = my_pos

    if bug.mode == BugMode.MODE_GOAL_SEEK:
        dx = target.x - my_pos.x
        dy = target.y - my_pos.y

        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)

        next_pos = Position(my_pos.x + step_x, my_pos.y + step_y)

        if (
            0 <= next_pos.x < w
            and 0 <= next_pos.y < h
            and cost_grid[(next_pos.y + pad) * pw + (next_pos.x + pad)] != INF
            and next_pos not in blocked
        ):
            return next_pos
        bug.mode = BugMode.MODE_WALL_FOLLOW
        bug.hit_point = my_pos

    if bug.mode == BugMode.MODE_WALL_FOLLOW:
        if (
            bug.hit_point
            and _on_baseline(my_pos, bug.start, target)
            and _chebyshev(my_pos, target) < _chebyshev(bug.hit_point, target)
        ):
            bug.mode = BugMode.MODE_GOAL_SEEK
            return bugnav_step(self, ct, target, blocked)

        goal_dx = target.x - my_pos.x
        goal_dy = target.y - my_pos.y
        ideal_angle = math.atan2(goal_dy, goal_dx)

        dirs = DIR8[:]

        def key(d: Direction) -> float:
            dx, dy = d.delta()
            return abs(math.atan2(dy, dx) - ideal_angle)

        dirs.sort(key=key)

        for d in dirs:
            n = my_pos.add(d)
            if not (0 <= n.x < w and 0 <= n.y < h):
                continue

            if cost_grid[(n.y + pad) * pw + (n.x + pad)] != INF and n not in blocked:
                return n

    return None


def bugnav(self: Builder, ct: Controller, target: Position) -> Position | None:
    blocked: set[Position] = set()
    my_pos = ct.get_position()
    for pos in ct.get_nearby_tiles():
        if pos != my_pos and ct.get_tile_builder_bot_id(pos) is not None:
            blocked.add(pos)

    return bugnav_step(self, ct, target, blocked)
