"""Shared helpers for bug-family SPSP algorithms.

Uses (x, y) coordinates internally; callers convert to/from flat bench_nav
indices at the plan() boundary.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

# Indexed 0..8: N, NE, E, SE, S, SW, W, NW — 45° increments clockwise.
DIRS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)
DIR_NAMES: tuple[str, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

# Wall-follow priority relative to `follow_dir`: -90°, -45°, 0°, +45°, +90°,
# +135°, +180°, -135°.
LEFT_HAND_PRIORITY: tuple[int, ...] = (6, 7, 0, 1, 2, 3, 4, 5)

# Builder bot vision radius squared.
VISION_R_SQ: int = 20


def rot_cw_90(d: int) -> int:
    return (d + 2) % 8


def rot_ccw_90(d: int) -> int:
    return (d + 6) % 8


def dist_sq(a: tuple[int, int], b: tuple[int, int]) -> int:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def _sign(x: int) -> int:
    return (x > 0) - (x < 0)


def dir_to_goal(pos: tuple[int, int], goal: tuple[int, int]) -> int:
    dx = _sign(goal[0] - pos[0])
    dy = _sign(goal[1] - pos[1])
    return direction_to_cell_delta(dx, dy)


def direction_to_cell(from_: tuple[int, int], to: tuple[int, int]) -> int:
    dx = _sign(to[0] - from_[0])
    dy = _sign(to[1] - from_[1])
    return direction_to_cell_delta(dx, dy)


def direction_to_cell_delta(dx: int, dy: int) -> int:
    match (dx, dy):
        case (0, -1):
            return 0
        case (1, -1):
            return 1
        case (1, 0):
            return 2
        case (1, 1):
            return 3
        case (0, 1):
            return 4
        case (-1, 1):
            return 5
        case (-1, 0):
            return 6
        case (-1, -1):
            return 7
        case _:
            return 0


def neighbour(pos: tuple[int, int], dir_: int) -> tuple[int, int]:
    d = DIRS[dir_]
    return (pos[0] + d[0], pos[1] + d[1])


def follow_step(
    pos: tuple[int, int],
    follow_dir: int,
    passable: Callable[[int, int], bool],
) -> tuple[tuple[int, int], int] | None:
    """Left-hand wall-follow step; first passable neighbour wins."""
    for off in LEFT_HAND_PRIORITY:
        nd = (follow_dir + off) % 8
        np = neighbour(pos, nd)
        if passable(np[0], np[1]):
            return np, nd
    return None


@dataclass
class WallFollowState:
    """Wall-follow state anchored to a specific obstacle cell."""

    pos: tuple[int, int]
    current_obstacle: tuple[int, int]
    obstacle_on_right: bool
    """True = right-hand-on-wall (rotate CCW). False = left-hand (CW)."""


class WallStepOutcome(Enum):
    MOVED = 0
    SURROUNDED = 1


def wall_follow_step(
    state: WallFollowState,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
) -> WallStepOutcome:
    """Canonical wall-follow step — see _common.rs for full semantics."""
    return _wall_follow_step_inner(state, passable, on_map, can_flip=True)


def _wall_follow_step_inner(
    state: WallFollowState,
    passable: Callable[[int, int], bool],
    on_map: Callable[[int, int], bool],
    *,
    can_flip: bool,
) -> WallStepOutcome:
    direction = direction_to_cell(state.pos, state.current_obstacle)
    for _ in range(8):
        if state.obstacle_on_right:
            direction = (direction + 7) % 8  # CCW
        else:
            direction = (direction + 1) % 8  # CW
        nxt = neighbour(state.pos, direction)
        if passable(nxt[0], nxt[1]):
            state.pos = nxt
            return WallStepOutcome.MOVED
        if on_map(nxt[0], nxt[1]):
            state.current_obstacle = nxt
        elif can_flip:
            state.obstacle_on_right = not state.obstacle_on_right
            return _wall_follow_step_inner(state, passable, on_map, can_flip=False)
    return WallStepOutcome.SURROUNDED


def sensed_cells(origin: tuple[int, int]) -> list[tuple[int, int]]:
    """All cells within sensor range of origin (69 cells including origin)."""
    return [
        (origin[0] + dx, origin[1] + dy)
        for dy in range(-4, 5)
        for dx in range(-4, 5)
        if dx * dx + dy * dy <= VISION_R_SQ
    ]


def has_los(
    from_: tuple[int, int],
    target: tuple[int, int],
    passable: Callable[[int, int], bool],
) -> bool:
    """True iff target is within sensor range of from AND every cell on the
    Bresenham line (exclusive of `from`) is passable."""
    if dist_sq(from_, target) > VISION_R_SQ:
        return False
    line = bresenham(from_, target)
    return all(passable(p[0], p[1]) for p in line[1:])


def farthest_visible_along(
    from_: tuple[int, int],
    toward: tuple[int, int],
    passable: Callable[[int, int], bool],
) -> tuple[int, int]:
    """Farthest passable cell along the Bresenham line from `from` toward
    `toward`, capped at sensor range. Returns `from` if immediately blocked."""
    if from_ == toward:
        return from_
    line = bresenham(from_, toward)
    last_clear = from_
    for p in line[1:]:
        if dist_sq(from_, p) > VISION_R_SQ:
            break
        if not passable(p[0], p[1]):
            break
        last_clear = p
    return last_clear


_DIRS8: tuple[tuple[int, int], ...] = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


def local_bfs(
    start: tuple[int, int],
    passable: Callable[[int, int], bool],
) -> dict[tuple[int, int], tuple[int, int]]:
    """Local 8-connected BFS from `start` over cells within sensor range.
    Returns parent map (start not included)."""
    queue: deque[tuple[int, int]] = deque([start])
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    visited: set[tuple[int, int]] = {start}
    while queue:
        p = queue.popleft()
        for dx, dy in _DIRS8:
            n = (p[0] + dx, p[1] + dy)
            if dist_sq(start, n) > VISION_R_SQ:
                continue
            if not passable(n[0], n[1]):
                continue
            if n in visited:
                continue
            visited.add(n)
            parent[n] = p
            queue.append(n)
    return parent


def bresenham(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Integer Bresenham line from a (inclusive) to b (inclusive)."""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    out: list[tuple[int, int]] = []
    while True:
        out.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return out


# === Bench_nav integration helpers ========================================


def make_passable_closures(
    w: int, h: int, cost: list[int], inf: int
) -> tuple[Callable[[int, int], bool], Callable[[int, int], bool]]:
    """Build `passable(x, y)` and `on_map(x, y)` closures over a flat cost grid."""

    def passable(x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= w or y >= h:
            return False
        return cost[y * w + x] < inf

    def on_map(x: int, y: int) -> bool:
        return 0 <= x < w and 0 <= y < h

    return passable, on_map
