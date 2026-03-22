"""Bug2 pathfinding using game-native Position and Direction types.

All functions operate on Position (NamedTuple) and Direction (Enum)
from the cambc engine, avoiding raw tuple/int-index overhead.
"""

from typing import Literal

from cambc import Direction, Position

# ── Direction utilities ─────────────────────────────────────────────

# 8 directions in clockwise order (matching engine convention)
_ALL_DIRS = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
_DIR_IDX = {d: i for i, d in enumerate(_ALL_DIRS)}

# Precomputed neighbor directions (all 8)
_NEIGHBOR_DIRS = _ALL_DIRS


def _rotate(d: Direction, steps: int) -> Direction:
    """Rotate direction by steps * 45° clockwise (negative = CCW)."""
    return _ALL_DIRS[(_DIR_IDX[d] + steps) % 8]


# ── Core helpers ────────────────────────────────────────────────────


def chebyshev(a: Position, b: Position) -> int:
    """Chebyshev (king-move) distance between two Positions."""
    return max(abs(a.x - b.x), abs(a.y - b.y))


def in_vision(origin: Position, cell: Position) -> bool:
    """Check if cell is within builder bot vision radius (r² <= 20)."""
    return origin.distance_squared(cell) <= 20


def _bresenham_step(
    x: int, y: int, err: int, adx: int, ady: int, sx: int, sy: int
) -> tuple[int, int, int]:
    """Advance one Bresenham step. Returns (x, y, err)."""
    e2 = 2 * err
    if e2 > -ady:
        err -= ady
        x += sx
    if e2 < adx:
        err += adx
        y += sy
    return x, y, err


def _make_line_state(
    pos: Position,
    target: Position,
) -> tuple[int, int, Literal[1, -1, 0], Literal[1, -1, 0], int]:
    """Compute Bresenham parameters for a line from pos toward target.
    Returns (adx, ady, sx, sy, err)."""
    adx = abs(target.x - pos.x)
    ady = abs(target.y - pos.y)
    sx = 1 if pos.x < target.x else -1 if pos.x > target.x else 0
    sy = 1 if pos.y < target.y else -1 if pos.y > target.y else 0
    return adx, ady, sx, sy, adx - ady


def scan_line(pos, target, walkable):
    """Walk a Bresenham line from pos toward target within vision.
    Returns (furthest_walkable, first_wall).
    furthest_walkable: last walkable cell before a wall or vision edge, or None.
    first_wall: first non-walkable cell within vision, or None."""
    if pos == target:
        return None, None
    x, y = pos.x, pos.y
    adx, ady, sx, sy, err = _make_line_state(pos, target)
    furthest = None
    while True:
        x, y, err = _bresenham_step(x, y, err, adx, ady, sx, sy)
        cell = Position(x, y)
        if not in_vision(pos, cell):
            break
        if cell not in walkable:
            return furthest, cell
        furthest = cell
        if cell == target:
            break
    return furthest, None


def _step_along_line(current, target, walkable, line_state):
    """Take one Bresenham step from current toward target.
    Returns (next_cell, blocked_direction_or_None, new_line_state)."""
    if current == target:
        return current, None, line_state
    ls_adx, ls_ady, ls_sx, ls_sy, ls_err = line_state
    x, y = current.x, current.y
    x, y, new_err = _bresenham_step(x, y, ls_err, ls_adx, ls_ady, ls_sx, ls_sy)
    cell = Position(x, y)
    new_state = (ls_adx, ls_ady, ls_sx, ls_sy, new_err)
    if cell not in walkable:
        return current, current.direction_to(cell), None
    return cell, None, new_state


def has_line_of_sight(pos, target, walkable):
    """Check if target is reachable from pos along a clear Bresenham line."""
    furthest, _ = scan_line(pos, target, walkable)
    return furthest == target


def _trace_step(sim_pos, sim_dir, trace_left, walkable, origin):
    """Take one wall-following step. Returns (new_pos, new_dir) or None if stuck/out of vision."""
    next_pos = sim_pos.add(sim_dir)
    if not in_vision(origin, next_pos):
        return None
    if next_pos in walkable:
        sim_dir = _rotate(sim_dir, 2 if trace_left else -2)
        return next_pos, sim_dir

    for _ in range(8):
        sim_dir = _rotate(sim_dir, -1 if trace_left else 1)
        next_pos = sim_pos.add(sim_dir)
        if not in_vision(origin, next_pos):
            return None
        if next_pos in walkable:
            sim_dir = _rotate(sim_dir, 2 if trace_left else -2)
            return next_pos, sim_dir
    return None


def _trace_move(current, tracing_dir, trace_left, walkable):
    """Take one wall-following move. Returns (next_pos, new_dir) or (None, dir)."""
    next_pos = current.add(tracing_dir)
    if next_pos in walkable:
        tracing_dir = _rotate(tracing_dir, 2 if trace_left else -2)
        return next_pos, tracing_dir
    for _ in range(8):
        tracing_dir = _rotate(tracing_dir, -1 if trace_left else 1)
        next_pos = current.add(tracing_dir)
        if next_pos in walkable:
            tracing_dir = _rotate(tracing_dir, 2 if trace_left else -2)
            return next_pos, tracing_dir
    return None, tracing_dir


# ── Agent state & step ──────────────────────────────────────────────


class AgentState:
    """Holds all mutable state for one Bug2 agent."""

    def __init__(self, start, goal) -> None:
        self.start = start
        self.goal = goal
        self.current = start
        self.prev = start
        self.is_tracing = False
        self.checkpoint_dist = chebyshev(start, goal)
        self.detour_dist = self.checkpoint_dist
        self.obstacle_start_pos = None
        self.tracing_dir = Direction.NORTH
        self.trace_left = None
        self.trace_heads = None
        self.line_state = _make_line_state(start, goal)
        self.prev_target = goal
        self.reached = False
        # Debug: last scan_line results (set by bug2_step each call)
        self.dbg_last_open = None
        self.dbg_first_wall = None

    @property
    def done(self) -> bool:
        return self.reached

    def retarget(self, current: Position, goal: Position) -> None:
        """Reset state for a new goal while keeping the agent at current."""
        self.start = current
        self.goal = goal
        self.current = current
        self.prev = current
        self.is_tracing = False
        self.checkpoint_dist = chebyshev(current, goal)
        self.detour_dist = self.checkpoint_dist
        self.obstacle_start_pos = None
        self.tracing_dir = Direction.NORTH
        self.trace_left = None
        self.trace_heads = None
        self.line_state = _make_line_state(current, goal)
        self.prev_target = goal
        self.reached = False


def bug2_step(agent: AgentState, pos: Position, walkable, occupied):
    """Advance one Bug2 step for a single agent.
    occupied is the set of Positions occupied by OTHER agents this turn.
    Returns the new Position (may be unchanged if blocked by another agent)."""

    # Sync agent position with external state
    moved = pos != agent.current
    if moved:
        agent.current = pos
        if agent.is_tracing:
            agent.trace_left = None
            agent.is_tracing = False
            agent.line_state = _make_line_state(pos, agent.goal)
            agent.prev_target = agent.goal
            agent.reached = agent.current == agent.goal

    if agent.done:
        return agent.current

    current = agent.current
    prev = agent.prev
    goal = agent.goal

    if current == goal:
        agent.reached = True
        return current

    cur_dist = chebyshev(current, goal)
    next_pos = None

    # Scan line to goal
    last_open, first_wall = scan_line(current, goal, walkable)
    agent.dbg_last_open = last_open
    agent.dbg_first_wall = first_wall

    not_adj_to_wall = all(current.add(d) in walkable for d in _NEIGHBOR_DIRS)

    target = goal

    if agent.is_tracing:
        lookahead = last_open
        exit_trace = not_adj_to_wall
        if (
            lookahead is not None
            and chebyshev(lookahead, prev) > 0
            and chebyshev(lookahead, goal) < agent.checkpoint_dist
        ):
            agent.checkpoint_dist = chebyshev(lookahead, goal)
            agent.obstacle_start_pos = lookahead
            exit_trace = True

        if exit_trace:
            agent.trace_left = None
            agent.is_tracing = False
            agent.line_state = _make_line_state(current, goal)
            agent.prev_target = goal
            # Fall through to non-tracing
        else:
            next_pos, agent.tracing_dir = _trace_move(
                current,
                agent.tracing_dir,
                agent.trace_left,
                walkable,
            )
            if next_pos is None:
                return current  # stuck

    if not agent.is_tracing:
        wall_visible = first_wall is not None

        if wall_visible and agent.trace_heads is None:
            trace_start = last_open if last_open is not None else current
            wall_dir = trace_start.direction_to(first_wall)
            agent.trace_heads = [
                [trace_start, wall_dir, trace_start],
                [trace_start, wall_dir, trace_start],
            ]

        elif not wall_visible:
            agent.trace_heads = None

        if agent.trace_heads is not None:
            for side in range(2):
                pos_h, dir_h, los_h = agent.trace_heads[side]
                is_left = side == 0
                for _ in range(5):
                    result = _trace_step(pos_h, dir_h, is_left, walkable, current)
                    if result is None:
                        break
                    pos_h, dir_h = result
                    if has_line_of_sight(current, pos_h, walkable):
                        los_h = pos_h
                agent.trace_heads[side] = [pos_h, dir_h, los_h]

        if agent.trace_heads is not None:
            gx = goal.x - current.x
            gy = goal.y - current.y

            l_los = agent.trace_heads[0][2]
            r_los = agent.trace_heads[1][2]
            l_gone = chebyshev(l_los, agent.trace_heads[0][0])
            r_gone = chebyshev(r_los, agent.trace_heads[1][0])
            l_dist = chebyshev(l_los, goal)
            r_dist = chebyshev(r_los, goal)

            l_dx = l_los.x - current.x
            l_dy = l_los.y - current.y
            l_valid = (l_dx != 0 or l_dy != 0) and l_dx * gx + l_dy * gy >= -3

            r_dx = r_los.x - current.x
            r_dy = r_los.y - current.y
            r_valid = (r_dx != 0 or r_dy != 0) and r_dx * gx + r_dy * gy >= -3

            if l_gone > r_gone and l_valid:
                if not_adj_to_wall:
                    target = l_los
                agent.trace_left = True
            elif r_gone > l_gone and r_valid:
                if not_adj_to_wall:
                    target = r_los
                agent.trace_left = False
            elif l_dist < r_dist and l_dist <= agent.detour_dist and l_valid:
                if l_dist < agent.detour_dist:
                    target = l_los
                    agent.detour_dist = l_dist
                agent.trace_left = True
            elif r_dist < l_dist and r_dist <= agent.detour_dist and r_valid:
                if r_dist < agent.detour_dist:
                    target = r_los
                    agent.detour_dist = r_dist
                agent.trace_left = False
            elif l_valid and not r_valid:
                agent.trace_left = True
            elif r_valid and not l_valid:
                agent.trace_left = False

        # Reset line_state if target changed
        if target != agent.prev_target:
            agent.line_state = _make_line_state(current, target)
            agent.prev_target = target

        next_cell, blocked, agent.line_state = _step_along_line(
            current,
            target,
            walkable,
            agent.line_state,
        )

        if blocked is not None:
            if cur_dist < agent.checkpoint_dist:
                agent.checkpoint_dist = cur_dist
                agent.obstacle_start_pos = current
            agent.tracing_dir = blocked
            agent.trace_heads = None

            if agent.trace_left is None:
                goal_dir = current.direction_to(goal)
                left_diff = (_DIR_IDX[blocked] - _DIR_IDX[goal_dir]) % 8
                right_diff = (_DIR_IDX[goal_dir] - _DIR_IDX[blocked]) % 8
                agent.trace_left = left_diff <= right_diff

            next_pos, agent.tracing_dir = _trace_move(
                current,
                agent.tracing_dir,
                agent.trace_left,
                walkable,
            )
            agent.is_tracing = True
        else:
            next_pos = next_cell

    if next_pos is None:
        return current

    # Can't move onto a tile occupied by another agent — try nearby directions
    if next_pos in occupied:
        desired_dir = current.direction_to(next_pos)
        # Alternate CW/CCW: +1, -1, +2, -2, +3, -3 (skip opposite ±4)
        for offset in [1, -1, 2, -2, 3, -3]:
            alt_dir = _rotate(desired_dir, offset)
            alt_pos = current.add(alt_dir)
            if alt_pos in walkable and alt_pos not in occupied:
                next_pos = alt_pos
                if agent.is_tracing:
                    agent.trace_left = None
                    agent.is_tracing = False
                    agent.prev_target = goal
                agent.line_state = _make_line_state(next_pos, goal)
                break
        else:
            return current  # no alternative, wait

    agent.prev = current
    agent.current = next_pos

    if agent.current == goal:
        agent.reached = True

    return agent.current
