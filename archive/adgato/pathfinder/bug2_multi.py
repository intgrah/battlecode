"""Multi-agent Bug2: each agent runs independent Bug2 logic, one move per step.
Agents cannot occupy the same tile — if a move is blocked by another agent,
the agent waits that turn.
"""

import os
import random

import matplotlib.pyplot as plt
from bug2 import (
    DIR_INDEX,
    NEIGHBORS,
    _trace_move,
    _trace_step,
    direction_to,
    dist,
    has_line_of_sight,
    in_vision,
    load_map,
    make_line_state,
    move,
    scan_line,
    step_along_line,
)

# Per-agent colors (RGBA for drawing, RGB01 for legend)
AGENT_COLORS = [
    ((255, 0, 255, 255), (1, 0, 1), "magenta"),
    ((0, 200, 255, 255), (0, 0.78, 1), "cyan"),
    ((255, 165, 0, 255), (1, 0.65, 0), "orange"),
    ((180, 0, 255, 255), (0.71, 0, 1), "purple"),
    ((0, 255, 100, 255), (0, 1, 0.39), "green"),
    ((255, 255, 0, 255), (1, 1, 0), "yellow"),
]

GOAL_COLORS = [
    ((200, 0, 200, 255), (0.78, 0, 0.78), "magenta goal"),
    ((0, 150, 200, 255), (0, 0.59, 0.78), "cyan goal"),
    ((200, 120, 0, 255), (0.78, 0.47, 0), "orange goal"),
    ((130, 0, 200, 255), (0.51, 0, 0.78), "purple goal"),
    ((0, 200, 70, 255), (0, 0.78, 0.27), "green goal"),
    ((200, 200, 0, 255), (0.78, 0.78, 0), "yellow goal"),
]


class AgentState:
    """Holds all mutable state for one Bug2 agent."""

    def __init__(self, start, goal) -> None:
        self.start = start
        self.goal = goal
        self.current = start
        self.prev = start
        self.path = [start]
        self.is_tracing = False
        self.checkpoint_dist = dist(start, goal)
        self.detour_dist = self.checkpoint_dist
        self.obstacle_start_pos = None
        self.tracing_dir = 0
        self.trace_left = None
        self.trace_heads = None
        self.line_state = make_line_state(start, goal)
        self.prev_target = goal
        self.reached = False

    @property
    def done(self):
        return self.reached


def bug2_step(agent, walkable, occupied):
    """Advance one Bug2 step for a single agent.
    occupied is the set of cells occupied by OTHER agents this turn.
    Returns the new position (may be unchanged if blocked by another agent).
    """
    if agent.done:
        return agent.current

    current = agent.current
    prev = agent.prev
    goal = agent.goal

    if current == goal:
        agent.reached = True
        return current

    cur_dist = dist(current, goal)
    next_pos = None

    # Scan line to goal
    last_open, first_wall = scan_line(current, goal, walkable)

    not_adj_to_wall = all(
        (current[0] + dx, current[1] + dy) in walkable for dx, dy in NEIGHBORS
    )

    if agent.is_tracing:
        lookahead = last_open
        exit_trace = not_adj_to_wall
        if (
            lookahead is not None
            and dist(lookahead, prev) > 0
            and dist(lookahead, goal) < agent.checkpoint_dist
        ):
            agent.checkpoint_dist = dist(lookahead, goal)
            agent.obstacle_start_pos = lookahead
            exit_trace = True

        if exit_trace:
            agent.trace_left = None
            agent.is_tracing = False
            agent.line_state = make_line_state(current, goal)
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
            wall_dir = direction_to(trace_start, first_wall)
            agent.trace_heads = [
                [trace_start, wall_dir, trace_start],
                [trace_start, wall_dir, trace_start],
            ]

        elif not wall_visible:
            agent.trace_heads = None

        dist(last_open, goal) if last_open is not None else cur_dist

        if agent.trace_heads is not None:
            for side in range(2):
                pos_h, dir_h, los_h = agent.trace_heads[side]
                is_left = side == 0
                for _ in range(5):
                    if not in_vision(current, pos_h):
                        break
                    result = _trace_step(pos_h, dir_h, is_left, walkable, current)
                    if result is None:
                        break
                    pos_h, dir_h = result
                    if has_line_of_sight(current, pos_h, walkable):
                        los_h = pos_h
                    else:
                        break
                agent.trace_heads[side] = [pos_h, dir_h, los_h]

        target = goal
        if agent.trace_heads is not None:
            gx = goal[0] - current[0]
            gy = goal[1] - current[1]

            l_los = agent.trace_heads[0][2]
            r_los = agent.trace_heads[1][2]
            l_gone = dist(l_los, agent.trace_heads[0][0])
            r_gone = dist(r_los, agent.trace_heads[1][0])
            l_dist = dist(l_los, goal)
            r_dist = dist(r_los, goal)

            l_dx = l_los[0] - current[0]
            l_dy = l_los[1] - current[1]
            l_valid = (l_dx != 0 or l_dy != 0) and l_dx * gx + l_dy * gy >= -3

            r_dx = r_los[0] - current[0]
            r_dy = r_los[1] - current[1]
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
            agent.line_state = make_line_state(current, target)
            agent.prev_target = target

        next_cell, blocked, agent.line_state = step_along_line(
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
                goal_dir = direction_to(current, goal)
                left_diff = (blocked - goal_dir) % 8
                right_diff = (goal_dir - blocked) % 8
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
        desired_dir = DIR_INDEX[(next_pos[0] - current[0], next_pos[1] - current[1])]
        # Alternate CW/CCW: +1, -1, +2, -2, +3, -3 (skip opposite ±4)
        for offset in [1, -1, 2, -2, 3, -3]:
            alt_dir = (desired_dir + offset) % 8
            alt_pos = move(current, alt_dir)
            if alt_pos in walkable and alt_pos not in occupied:
                next_pos = alt_pos
                break
        else:
            return current  # no alternative, wait

    agent.prev = current
    agent.current = next_pos
    agent.path.append(next_pos)

    if agent.current == goal:
        agent.reached = True

    return agent.current


def _draw_multi_frame(img, step, agents, temp_walls, w, h) -> None:
    """Draw one debug frame showing all agents."""
    frame = img.copy()
    px = frame.load()

    # Draw temporary walls in dark red
    for wx, wy in temp_walls:
        if 0 <= wx < w and 0 <= wy < h:
            px[wx, wy] = (180, 40, 40, 255)

    # Draw current positions (on top)
    for i, agent in enumerate(agents):
        color = AGENT_COLORS[i % len(AGENT_COLORS)][0]
        cx, cy = agent.current
        if 0 <= cx < w and 0 <= cy < h:
            px[cx, cy] = color

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.set_facecolor("grey")
    ax.imshow(frame)
    ax.axis("off")

    plt.savefig(f"frames/step_{step:03d}.png", dpi=150, bbox_inches="tight")
    plt.close()


def run_multi(
    agent_configs,
    walkable,
    max_steps=80,
    debug_img=None,
    temp_wall_count=5,
    rng=None,
):
    """Run multiple independent Bug2 agents.
    agent_configs: list of (start, goal) tuples.
    temp_wall_count: number of temporary walls active at any time.
    Returns list of (path, reached) per agent.
    """
    if rng is None:
        rng = random.Random()
    agents = [AgentState(s, g) for s, g in agent_configs]
    walkable = set(walkable)  # mutable copy
    walkable_list = list(walkable)
    # temp_walls: dict of cell -> steps remaining
    temp_walls = {}

    if debug_img is not None:
        os.makedirs("frames", exist_ok=True)
        d_img, d_w, d_h = debug_img
        max_frames = 200

    for step in range(max_steps):
        if all(a.done for a in agents):
            break

        # Expire temp walls
        expired = [cell for cell, ttl in temp_walls.items() if ttl <= 0]
        for cell in expired:
            del temp_walls[cell]
            walkable.add(cell)

        # Spawn new temp walls to maintain target count
        positions = {a.current for a in agents}
        goals = {a.goal for a in agents}
        while len(temp_walls) < temp_wall_count:
            cell = rng.choice(walkable_list)
            if cell in walkable and cell not in positions and cell not in goals:
                walkable.discard(cell)
                temp_walls[cell] = rng.randint(1, 5)
            # walkable_list may have stale entries but that's fine,
            # the checks above filter them out

        # Tick down temp wall timers
        for cell in temp_walls:
            temp_walls[cell] -= 1

        if debug_img is not None and step < max_frames:
            _draw_multi_frame(d_img, step, agents, temp_walls, d_w, d_h)

        for agent in agents:
            if agent.done:
                continue
            # Occupied = all other agents' current positions
            others = positions - {agent.current}
            old_pos = agent.current
            bug2_step(agent, walkable, others)
            # Update positions set
            if agent.current != old_pos:
                positions.discard(old_pos)
                positions.add(agent.current)

    # Final frame
    if debug_img is not None:
        _draw_multi_frame(d_img, step, agents, temp_walls, d_w, d_h)

    return [(a.path, a.reached) for a in agents]


def main() -> None:
    img, walkable, w, h = load_map("testmap3.png")

    n_agents = 30
    temp_wall_count = 100
    rng = random.Random(42)
    walkable_list = list(walkable)
    used = set()
    agent_configs = []
    for _ in range(n_agents):
        s = rng.choice(walkable_list)
        while s in used:
            s = rng.choice(walkable_list)
        used.add(s)
        g = rng.choice(walkable_list)
        while g in used:
            g = rng.choice(walkable_list)
        used.add(g)
        agent_configs.append((s, g))

    print(f"Map: ({w}x{h}, {len(walkable)} walkable)")
    print(f"Running {len(agent_configs)} agents...")

    results = run_multi(
        agent_configs,
        walkable,
        max_steps=80,
        temp_wall_count=temp_wall_count,
        debug_img=(img, w, h),
    )

    for i, (path, reached) in enumerate(results):
        s, g = agent_configs[i]
        status = "REACHED" if reached else "FAILED"
        print(f"  Agent {i}: {s}->{g} | {status} | {len(path) - 1} steps")


if __name__ == "__main__":
    main()
