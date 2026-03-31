import heapq
import os
import random

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from PIL import Image

NEIGHBORS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def load_map(path):
    img = Image.open(path).convert("RGBA")
    pixels = img.load()
    w, h = img.size
    walkable = set()
    for y in range(h):
        for x in range(w):
            r, g, b, _a = pixels[x, y]
            if r > 128 and g > 128 and b > 128:
                walkable.add((x, y))
    return img, walkable, w, h


def build_visibility_mask():
    """Build the 69-cell visibility mask offsets."""
    offsets = set()
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            offsets.add((dx, dy))
    for i in range(-2, 3):
        offsets.add((i, -4))
        offsets.add((i, 4))
        offsets.add((-4, i))
        offsets.add((4, i))
    return offsets


VISION_OFFSETS = build_visibility_mask()


def dist(a, b):
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy)


# 8 directions in clockwise order
DIRS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]

DIR_INDEX = {d: i for i, d in enumerate(DIRS)}


def direction_to(src, dst):
    dx = dst[0] - src[0]
    dy = dst[1] - src[1]
    if dx == 0 and dy == 0:
        return 0
    length = max(abs(dx), abs(dy))
    qdx = round(dx / length)
    qdy = round(dy / length)
    return DIR_INDEX[(qdx, qdy)]


def can_move(pos, dir_idx, walkable):
    dx, dy = DIRS[dir_idx]
    return (pos[0] + dx, pos[1] + dy) in walkable


def move(pos, dir_idx):
    dx, dy = DIRS[dir_idx]
    return (pos[0] + dx, pos[1] + dy)


def in_vision(origin, cell):
    """Check if cell is within the vision mask of origin."""
    return (cell[0] - origin[0], cell[1] - origin[1]) in VISION_OFFSETS


def _bresenham_step(x, y, err, adx, ady, sx, sy):
    """Advance one Bresenham step. Returns (x, y, err)."""
    e2 = 2 * err
    if e2 > -ady:
        err -= ady
        x += sx
    if e2 < adx:
        err += adx
        y += sy
    return x, y, err


def make_line_state(pos, target):
    """Compute Bresenham parameters for a line from pos toward target.
    Returns (adx, ady, sx, sy, err).
    """
    adx = abs(target[0] - pos[0])
    ady = abs(target[1] - pos[1])
    sx = 1 if pos[0] < target[0] else -1 if pos[0] > target[0] else 0
    sy = 1 if pos[1] < target[1] else -1 if pos[1] > target[1] else 0
    return adx, ady, sx, sy, adx - ady


def scan_line(pos, target, walkable):
    """Walk a Bresenham line from pos toward target within vision.
    Returns (furthest_walkable, first_wall).
    furthest_walkable: last walkable cell before a wall or vision edge, or None.
    first_wall: first non-walkable cell within vision, or None.
    """
    if pos == target:
        return None, None
    x, y = pos
    adx, ady, sx, sy, err = make_line_state(pos, target)
    furthest = None
    while True:
        x, y, err = _bresenham_step(x, y, err, adx, ady, sx, sy)
        cell = (x, y)
        if not in_vision(pos, cell):
            break
        if cell not in walkable:
            return furthest, cell
        furthest = cell
        if cell == target:
            break
    return furthest, None


def step_along_line(current, target, walkable, line_state):
    """Take one Bresenham step from current toward target.
    line_state must be set up by the caller via make_line_state.
    Returns (next_cell, blocked_dir_idx_or_None, new_line_state).
    """
    if current == target:
        return current, None, line_state
    ls_adx, ls_ady, ls_sx, ls_sy, ls_err = line_state
    x, y = current
    x, y, new_err = _bresenham_step(x, y, ls_err, ls_adx, ls_ady, ls_sx, ls_sy)
    cell = (x, y)
    new_state = (ls_adx, ls_ady, ls_sx, ls_sy, new_err)
    if cell not in walkable:
        return current, DIR_INDEX[(cell[0] - current[0], cell[1] - current[1])], None
    return cell, None, new_state


def has_line_of_sight(pos, target, walkable):
    """Check if target is reachable from pos along a clear Bresenham line."""
    furthest, _ = scan_line(pos, target, walkable)
    return furthest == target


def _trace_step(sim_pos, sim_dir, trace_left, walkable, origin):
    """Take one wall-following step. Returns (new_pos, new_dir) or None if stuck/out of vision."""
    next_pos = move(sim_pos, sim_dir)
    if not in_vision(origin, next_pos):
        return None
    if can_move(sim_pos, sim_dir, walkable):
        sim_dir = (sim_dir + (2 if trace_left else -2)) % 8
        return next_pos, sim_dir

    for _ in range(8):
        sim_dir = (sim_dir + (-1 if trace_left else 1)) % 8
        next_pos = move(sim_pos, sim_dir)
        if not in_vision(origin, next_pos):
            return None
        if can_move(sim_pos, sim_dir, walkable):
            sim_dir = (sim_dir + (2 if trace_left else -2)) % 8
            return next_pos, sim_dir
    return None


def _trace_move(current, tracing_dir, trace_left, walkable):
    """Take one wall-following move. Returns (next_pos, new_dir) or (None, dir)."""
    if can_move(current, tracing_dir, walkable):
        next_pos = move(current, tracing_dir)
        tracing_dir = (tracing_dir + (2 if trace_left else -2)) % 8
        return next_pos, tracing_dir
    for _ in range(8):
        tracing_dir = (tracing_dir + (-1 if trace_left else 1)) % 8
        if can_move(current, tracing_dir, walkable):
            next_pos = move(current, tracing_dir)
            tracing_dir = (tracing_dir + (2 if trace_left else -2)) % 8
            return next_pos, tracing_dir
    return None, tracing_dir


def _draw_frame(
    img,
    step,
    current,
    goal,
    path,
    is_tracing,
    trace_heads,
    obstacle_start_pos,
    lookahead,
    state,
    w,
    h,
) -> None:
    """Draw a debug frame and save to frames/."""
    frame = img.copy()
    px = frame.load()

    # Path so far in magenta
    for x, y in path:
        px[x, y] = (255, 0, 255, 255)

    # Obstacle start position in yellow
    if obstacle_start_pos is not None:
        ox, oy = obstacle_start_pos
        if 0 <= ox < w and 0 <= oy < h:
            px[ox, oy] = (255, 255, 0, 255)

    # Trace heads
    if trace_heads is not None:
        lp = trace_heads[0][0]  # left head position
        rp = trace_heads[1][0]  # right head position
        ll = trace_heads[0][2]  # left LOS target
        rl = trace_heads[1][2]  # right LOS target
        if 0 <= lp[0] < w and 0 <= lp[1] < h:
            px[lp[0], lp[1]] = (0, 255, 255, 255)
        if 0 <= rp[0] < w and 0 <= rp[1] < h:
            px[rp[0], rp[1]] = (255, 165, 0, 255)
        if ll != current and 0 <= ll[0] < w and 0 <= ll[1] < h:
            px[ll[0], ll[1]] = (0, 180, 180, 255)
        if rl != current and 0 <= rl[0] < w and 0 <= rl[1] < h:
            px[rl[0], rl[1]] = (200, 120, 0, 255)

    # Early exit lookahead in blue
    if lookahead is not None:
        lx, ly = lookahead
        if 0 <= lx < w and 0 <= ly < h:
            px[lx, ly] = (80, 120, 255, 255)

    # Current in green, goal in red (drawn last)
    px[current[0], current[1]] = (0, 200, 0, 255)
    px[goal[0], goal[1]] = (255, 0, 0, 255)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.set_facecolor("grey")
    ax.imshow(frame)
    ax.axis("off")

    info = f"Step {step}: {current} d={dist(current, goal)} | {state}"
    if is_tracing:
        info += " | tracing"
    if trace_heads:
        info += (
            f"\nL_head={trace_heads[0][0]} L_los={trace_heads[0][2]}"
            f" | R_head={trace_heads[1][0]} R_los={trace_heads[1][2]}"
        )

    patches = [
        mpatches.Patch(color=(0, 0.78, 0), label="Current"),
        mpatches.Patch(color=(1, 0, 0), label="Goal"),
        mpatches.Patch(color=(1, 0, 1), label="Path"),
        mpatches.Patch(color=(1, 1, 0), label="Obstacle start"),
    ]
    if trace_heads:
        patches += [
            mpatches.Patch(color=(0, 1, 1), label="L head"),
            mpatches.Patch(color=(1, 0.65, 0), label="R head"),
            mpatches.Patch(color=(0, 0.71, 0.71), label="L LOS"),
            mpatches.Patch(color=(0.78, 0.47, 0), label="R LOS"),
        ]
    if lookahead is not None:
        patches.append(mpatches.Patch(color=(0.31, 0.47, 1), label="Lookahead"))

    ax.legend(handles=patches, loc="upper right", fontsize=7)
    ax.set_title(info, fontsize=9)
    plt.savefig(f"frames/step_{step:03d}.png", dpi=150, bbox_inches="tight")
    plt.close()


def bug2(start, goal, walkable, max_steps=100, debug_img=None):
    """Bug2 pathfinding with visibility-enhanced tracing exit.
    Pass debug_img=(img, w, h) to save per-step frames to frames/.
    """
    path = [start]
    current = start
    prev = start
    is_tracing = False
    checkpoint_dist = dist(start, goal)
    detour_dist = checkpoint_dist
    obstacle_start_pos = None
    tracing_dir = 0
    trace_left = None
    trace_heads = None
    line_state = make_line_state(start, goal)
    prev_target = goal

    if debug_img is not None:
        os.makedirs("frames", exist_ok=True)
        d_img, d_w, d_h = debug_img
        frame_count = 0
        max_frames = 80

    for _step_num in range(max_steps):
        if current == goal:
            break

        lookahead = None
        state = "move"
        next_pos = None
        cur_dist = dist(current, goal)

        # Scan line to goal (used by both tracing and non-tracing)
        last_open, first_wall = scan_line(current, goal, walkable)

        not_adj_to_wall = all(
            (current[0] + dx, current[1] + dy) in walkable for dx, dy in NEIGHBORS
        )

        if is_tracing:
            lookahead = last_open
            exit_trace = not_adj_to_wall
            if (
                lookahead is not None
                and dist(lookahead, prev) > 0
                and dist(lookahead, goal) < checkpoint_dist
            ):
                checkpoint_dist = dist(lookahead, goal)
                obstacle_start_pos = lookahead
                exit_trace = True

            if exit_trace:
                trace_left = None
                state = "exit_trace"
                is_tracing = False
                line_state = make_line_state(current, goal)
                prev_target = goal
                # Fall through to non-tracing movement below
            else:
                state = "tracing"
                next_pos, tracing_dir = _trace_move(
                    current,
                    tracing_dir,
                    trace_left,
                    walkable,
                )
                if next_pos is None:
                    return path, False

        if not is_tracing:
            # --- Non-tracing: walk toward goal or detour target ---
            wall_visible = first_wall is not None

            if wall_visible and trace_heads is None:
                # Start trace heads at the cell just before the wall
                # [pos, dir, los_target, gone]
                trace_start = last_open if last_open is not None else current
                wall_dir = direction_to(trace_start, first_wall)
                trace_heads = [
                    [trace_start, wall_dir, trace_start],  # left
                    [trace_start, wall_dir, trace_start],  # right
                ]
            elif not wall_visible:
                trace_heads = None

            # Advance trace heads as far as possible within vision (max 5 per step each)
            if trace_heads is not None:
                for side in range(2):
                    pos_h, dir_h, los_h = trace_heads[side]
                    is_left = side == 0
                    for _ in range(5):
                        result = _trace_step(pos_h, dir_h, is_left, walkable, current)
                        if result is None:
                            break
                        pos_h, dir_h = result
                        if has_line_of_sight(current, pos_h, walkable):
                            los_h = pos_h
                    trace_heads[side] = [pos_h, dir_h, los_h]
                state = "detour"

            target = goal
            if trace_heads is not None:
                gx = goal[0] - current[0]
                gy = goal[1] - current[1]

                l_los = trace_heads[0][2]
                r_los = trace_heads[1][2]
                l_gone = dist(l_los, trace_heads[0][0])
                r_gone = dist(r_los, trace_heads[1][0])
                l_dist = dist(l_los, goal)
                r_dist = dist(r_los, goal)

                l_dx = l_los[0] - current[0]
                l_dy = l_los[1] - current[1]
                l_valid = (l_dx != 0 or l_dy != 0) and l_dx * gx + l_dy * gy >= -3

                r_dx = r_los[0] - current[0]
                r_dy = r_los[1] - current[1]
                r_valid = (r_dx != 0 or r_dy != 0) and r_dx * gx + r_dy * gy >= -3

                # Pick the head that has gone around the obstacle
                if l_gone > r_gone and l_valid:
                    if not_adj_to_wall:
                        target = l_los
                    trace_left = True
                elif r_gone > l_gone and r_valid:
                    if not_adj_to_wall:
                        target = r_los
                    trace_left = False

                elif l_dist < r_dist and l_dist <= detour_dist and l_valid:
                    if l_dist < detour_dist:
                        target = l_los
                        detour_dist = l_dist
                    trace_left = True
                elif r_dist < l_dist and r_dist <= detour_dist and r_valid:
                    if r_dist < detour_dist:
                        target = r_los
                        detour_dist = r_dist
                    trace_left = False

                elif l_valid and not r_valid:
                    trace_left = True
                elif r_valid and not l_valid:
                    trace_left = False

            # Reset line_state if target changed
            if target != prev_target:
                line_state = make_line_state(current, target)
                prev_target = target

            # Take one step toward target
            next_cell, blocked, line_state = step_along_line(
                current,
                target,
                walkable,
                line_state,
            )

            if blocked is not None:
                # Enter tracing and take the first trace step immediately
                if cur_dist < checkpoint_dist:
                    checkpoint_dist = cur_dist
                    obstacle_start_pos = current
                tracing_dir = blocked
                trace_heads = None
                state = "enter_trace"

                if trace_left is None:
                    # Pick trace direction so first move is toward goal
                    goal_dir = direction_to(current, goal)
                    # How far left vs right from blocked to goal direction
                    left_diff = (blocked - goal_dir) % 8
                    right_diff = (goal_dir - blocked) % 8
                    trace_left = left_diff <= right_diff

                next_pos, tracing_dir = _trace_move(
                    current,
                    tracing_dir,
                    trace_left,
                    walkable,
                )
                is_tracing = True
            else:
                next_pos = next_cell

        # Draw debug frame
        if debug_img is not None and frame_count < max_frames:
            _draw_frame(
                d_img,
                frame_count,
                current,
                goal,
                path,
                is_tracing,
                trace_heads,
                obstacle_start_pos,
                lookahead,
                state,
                d_w,
                d_h,
            )
            frame_count += 1

        # Position update
        prev = current
        current = next_pos
        if dist(prev, current) != 1:
            print(dist(prev, current), is_tracing, blocked is not None)
        assert dist(prev, current) == 1
        path.append(current)

    return path, current == goal


def dijkstra(start, goal, walkable):
    dist = {start: 0}
    prev = {}
    heap = [(0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == goal:
            break
        if d > dist.get(node, float("inf")):
            continue
        x, y = node
        for dx, dy in NEIGHBORS:
            nb = (x + dx, y + dy)
            if nb not in walkable:
                continue
            nd = d + 1
            if nd < dist.get(nb, float("inf")):
                dist[nb] = nd
                prev[nb] = node
                heapq.heappush(heap, (nd, nb))
    if goal not in prev and start != goal:
        return None
    path = []
    node = goal
    while node != start:
        path.append(node)
        node = prev[node]
    path.append(start)
    path.reverse()
    return path


def draw_paths(img, dijkstra_path, bug2_path, start, goal):
    img = img.copy()
    pixels = img.load()

    # Dijkstra in blue
    for x, y in dijkstra_path:
        pixels[x, y] = (80, 120, 255, 255)

    # Bug2 in magenta (drawn on top)
    for x, y in bug2_path:
        pixels[x, y] = (255, 0, 255, 255)

    # Start in green, goal in red
    pixels[start[0], start[1]] = (0, 200, 0, 255)
    pixels[goal[0], goal[1]] = (255, 0, 0, 255)

    return img


def main() -> None:
    import time

    img, walkable, w, h = load_map("testmap3.png")
    walkable_list = list(walkable)
    rng = random.Random(24)
    n_trials = 6000

    print(f"Map: ({w}x{h}, {len(walkable)} walkable)")
    print(f"Running {n_trials} trials...")

    wins = 0
    losses = 0
    ties = 0
    fails = 0
    ratios = []
    worst_ratio = 0
    worst_case = None

    bug2((4, 15), (46, 16), walkable, debug_img=(img, w, h))
    return

    t0 = time.time()
    for _i in range(n_trials):
        s = rng.choice(walkable_list)
        g = rng.choice(walkable_list)
        while g == s:
            g = rng.choice(walkable_list)

        d_path = dijkstra(s, g, walkable)
        if d_path is None:
            continue
        d_len = len(d_path) - 1

        b_path, reached = bug2(s, g, walkable)
        if not reached:
            print(f"fail {s}->{g}")
            fails += 1
            continue
        b_len = len(b_path) - 1

        ratio = b_len / d_len if d_len > 0 else 1.0
        ratios.append(ratio)
        if ratio < 1.0:
            wins += 1
        elif ratio > 1.0:
            losses += 1
        else:
            ties += 1
        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_case = (s, g, b_len, d_len)

    elapsed = time.time() - t0
    wins + losses + ties

    print(f"\nResults ({elapsed:.1f}s):")
    print(f"  Trials:  {n_trials} ({fails} failures)")
    print(f"  Wins:    {wins} (bug2 shorter)")
    print(f"  Ties:    {ties} (equal)")
    print(f"  Losses:  {losses} (dijkstra shorter)")
    if ratios:
        avg = sum(ratios) / len(ratios)
        median = sorted(ratios)[len(ratios) // 2]
        print(f"  Avg ratio:    {avg:.3f}")
        print(f"  Median ratio: {median:.3f}")
        print(
            f"  Worst ratio:  {worst_ratio:.2f} ({worst_case[0]}->{worst_case[1]}: bug2={worst_case[2]} dij={worst_case[3]})",
        )


if __name__ == "__main__":
    main()
