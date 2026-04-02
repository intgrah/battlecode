from collections.abc import Callable

from cambc import Controller, Direction, Position
from util import ib, wall

_DIRS = [d for d in Direction if d != Direction.CENTRE]


def _passable(ct: Controller, p: Position) -> bool:
    if not ib(ct, p):
        return False
    if not ct.is_in_vision(p):
        return True
    return not wall(ct, p)


def _bresenham(ax: int, ay: int, bx: int, by: int) -> set[tuple[int, int]]:
    locs: set[tuple[int, int]] = set()
    dx = bx - ax
    dy = by - ay
    sx = 1 if dx > 0 else -1 if dx < 0 else 0
    sy = 1 if dy > 0 else -1 if dy < 0 else 0
    dx = abs(dx)
    dy = abs(dy)
    d = max(dx, dy)
    r = d // 2
    x, y = ax, ay
    if dx >= dy:
        for _ in range(d):
            locs.add((x, y))
            x += sx
            r += dy
            if r >= dx:
                locs.add((x, y))
                y += sy
                r -= dx
    else:
        for _ in range(d):
            locs.add((x, y))
            y += sy
            r += dx
            if r >= dy:
                locs.add((x, y))
                x += sx
                r -= dy
    locs.add((x, y))
    return locs


class BugNav:
    def __init__(self) -> None:
        self.unreachable = False
        self._tracing = False
        self._tracing_dir: Direction | None = None
        self._obstacle_start_dist: int = 0
        self._trace_start: tuple[int, int] | None = None
        self._trace_steps: int = 0
        self._line: set[tuple[int, int]] = set()
        self._line_target: tuple[int, int] | None = None
        self._target: tuple[int, int] | None = None

    def reset(self) -> None:
        self.unreachable = False
        self._tracing = False
        self._tracing_dir = None
        self._obstacle_start_dist = 0
        self._trace_start = None
        self._trace_steps = 0
        self._line = set()
        self._line_target = None
        self._target = None

    def go(
        self,
        ct: Controller,
        target: Position,
        step_fn: Callable[[Direction], bool],
    ) -> bool:
        pos = ct.get_position()
        tx, ty = target.x, target.y

        if pos.x == tx and pos.y == ty:
            return False

        if self._target != (tx, ty):
            self._target = (tx, ty)
            self._tracing = False
            self._tracing_dir = None
            self._line_target = None

        if self._line_target != (tx, ty):
            self._line = _bresenham(pos.x, pos.y, tx, ty)
            self._line_target = (tx, ty)

        if not self._tracing:
            d = pos.direction_to(target)
            nxt = pos.add(d)
            if _passable(ct, nxt) and step_fn(d):
                return True
            self._tracing = True
            self._tracing_dir = d
            self._obstacle_start_dist = pos.distance_squared(target)
            self._trace_start = (pos.x, pos.y)
            self._trace_steps = 0

        if self._tracing:
            assert self._tracing_dir is not None
            self._trace_steps += 1
            if self._trace_start == (pos.x, pos.y) and self._trace_steps > 2:
                self.unreachable = True
                self._tracing = False
                return False
            cur_dist = pos.distance_squared(target)
            if (pos.x, pos.y) in self._line and cur_dist < self._obstacle_start_dist:
                self._tracing = False
                self._tracing_dir = None
                d = pos.direction_to(target)
                nxt = pos.add(d)
                if _passable(ct, nxt) and step_fn(d):
                    return True
                self._tracing = True
                self._tracing_dir = d
                self._obstacle_start_dist = cur_dist
                self._trace_start = (pos.x, pos.y)
                self._trace_steps = 0

            if self._tracing:
                for _ in range(9):
                    d = self._tracing_dir
                    assert d is not None
                    nxt = pos.add(d)
                    if _passable(ct, nxt):
                        if step_fn(d):
                            self._tracing_dir = d.rotate_right().rotate_right()
                            return True
                        break
                    self._tracing_dir = d.rotate_left()

        return False
