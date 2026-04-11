import math
from enum import IntEnum

from builder.state import State
from cambc import Controller, Position
from util import INF

__all__ = ["fallback_nav"]


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


_bug_states: dict[int, WallFollow] = {}


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


def fallback_step(
    state: State, ct: Controller, target: Position, blocked: set[Position] | None = None
) -> Position | None:
    unit_id = ct.get_id()
    curr = ct.get_position()

    if unit_id not in _bug_states or _bug_states[unit_id].goal != target:
        _bug_states[unit_id] = WallFollow(curr, target)

    bug = _bug_states[unit_id]
    if blocked is None:
        blocked = set()

    cost_grid = state.cost_grid
    w, h = state.w, state.h

    if curr == target:
        return None

    if bug.last_pos == curr and bug.mode == BugMode.MODE_GOAL_SEEK:
        bug.mode = BugMode.MODE_WALL_FOLLOW
        bug.hit_point = curr

    bug.last_pos = curr

    if bug.mode == BugMode.MODE_GOAL_SEEK:
        dx = target.x - curr.x
        dy = target.y - curr.y

        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)

        next_pos = Position(curr.x + step_x, curr.y + step_y)

        if (
            0 <= next_pos.x < w
            and 0 <= next_pos.y < h
            and cost_grid[next_pos.y * w + next_pos.x] != INF
            and next_pos not in blocked
        ):
            return next_pos
        bug.mode = BugMode.MODE_WALL_FOLLOW
        bug.hit_point = curr

    if bug.mode == BugMode.MODE_WALL_FOLLOW:
        if (
            bug.hit_point
            and _on_baseline(curr, bug.start, target)
            and _chebyshev(curr, target) < _chebyshev(bug.hit_point, target)
        ):
            bug.mode = BugMode.MODE_GOAL_SEEK
            return fallback_step(state, ct, target, blocked)

        dirs = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]

        goal_dx = target.x - curr.x
        goal_dy = target.y - curr.y
        ideal_angle = math.atan2(goal_dy, goal_dx)

        sorted_dirs = sorted(
            dirs, key=lambda d: abs(math.atan2(d[1], d[0]) - ideal_angle)
        )

        for dx, dy in sorted_dirs:
            nx, ny = curr.x + dx, curr.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue

            pos = Position(nx, ny)
            if cost_grid[ny * w + nx] != INF and pos not in blocked:
                return pos

    return None


def fallback_nav(state: State, ct: Controller, target: Position) -> Position | None:
    blocked: set[Position] = set()
    current_pos = ct.get_position()
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if pos != current_pos and ct.get_tile_builder_bot_id(pos) is not None:
            blocked.add(pos)

    return fallback_step(state, ct, target, blocked)
