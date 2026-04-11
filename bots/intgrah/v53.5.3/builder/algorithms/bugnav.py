import math
from enum import IntEnum

from builder.state import State
from cambc import Controller, Position
from util import INF, chebyshev

__all__ = ["bugnav"]


class BugNavMode(IntEnum):
    MODE_GOAL_SEEK = 0
    MODE_WALL_FOLLOW = 1


class BugNavState:
    def __init__(self, start: Position, goal: Position) -> None:
        self.mode = BugNavMode.MODE_GOAL_SEEK
        self.start = start
        self.goal = goal
        self.hit_point: Position | None = None
        self.last_pos: Position | None = None
        self.direction = 1


_bugnav_state: BugNavState | None = None


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
    state: State, ct: Controller, target: Position, blocked: set[Position] | None = None
) -> Position | None:
    global _bugnav_state  # noqa: PLW0603
    my_pos = ct.get_position()

    if _bugnav_state is None or _bugnav_state.goal != target:
        _bugnav_state = BugNavState(my_pos, target)
    bug: BugNavState = _bugnav_state

    if blocked is None:
        blocked = set()

    cost_grid = state.nav_cost
    w, h = state.w, state.h

    if my_pos == target:
        return None

    if bug.last_pos == my_pos and bug.mode == BugNavMode.MODE_GOAL_SEEK:
        bug.mode = BugNavMode.MODE_WALL_FOLLOW
        bug.hit_point = my_pos

    bug.last_pos = my_pos

    if bug.mode == BugNavMode.MODE_GOAL_SEEK:
        dx = target.x - my_pos.x
        dy = target.y - my_pos.y

        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)

        next_pos = Position(my_pos.x + step_x, my_pos.y + step_y)

        if (
            0 <= next_pos.x < w
            and 0 <= next_pos.y < h
            and cost_grid[next_pos.y * w + next_pos.x] != INF
            and next_pos not in blocked
        ):
            return next_pos
        bug.mode = BugNavMode.MODE_WALL_FOLLOW
        bug.hit_point = my_pos

    if bug.mode == BugNavMode.MODE_WALL_FOLLOW:
        if (
            bug.hit_point
            and _on_baseline(my_pos, bug.start, target)
            and chebyshev(my_pos, target) < chebyshev(bug.hit_point, target)
        ):
            bug.mode = BugNavMode.MODE_GOAL_SEEK
            return bugnav_step(state, ct, target, blocked)

        dirs = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]

        goal_dx = target.x - my_pos.x
        goal_dy = target.y - my_pos.y
        ideal_angle = math.atan2(goal_dy, goal_dx)

        sorted_dirs = sorted(
            dirs, key=lambda d: abs(math.atan2(d[1], d[0]) - ideal_angle)
        )

        for dx, dy in sorted_dirs:
            nx, ny = my_pos.x + dx, my_pos.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue

            pos = Position(nx, ny)
            if cost_grid[ny * w + nx] != INF and pos not in blocked:
                return pos

    return None


def bugnav(state: State, ct: Controller, target: Position) -> Position | None:
    blocked: set[Position] = set()
    current_pos = ct.get_position()
    nearby_positions = ct.get_nearby_tiles(2)
    for pos in nearby_positions:
        if pos != current_pos and ct.get_tile_builder_bot_id(pos) is not None:
            blocked.add(pos)

    return bugnav_step(state, ct, target, blocked)
