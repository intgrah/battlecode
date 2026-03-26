"""Compare bug2: old find_detour_target (all perimeter) vs new (two adjacent dirs)."""
import random
import time
from bug2 import (load_map, bug2, dijkstra, dist, direction_to,
                  step_along_line, create_thin_line, visible_from,
                  furthest_visible_on_line, create_line,
                  can_move, move, rotate_left, rotate_right,
                  _simulate_trace, VISION_PERIMETER, DIRS)

bug2_new = bug2


def find_detour_target_old(pos, goal, walkable):
    """Old version: scan all forward-facing perimeter cells."""
    gx, gy = goal[0] - pos[0], goal[1] - pos[1]
    best = None
    best_dist = float("inf")
    for dx, dy in VISION_PERIMETER:
        if dx * gx + dy * gy <= 0:
            continue
        perimeter_cell = (pos[0] + dx, pos[1] + dy)
        furthest = furthest_visible_on_line(pos, perimeter_cell, walkable)
        if furthest is not None:
            d = dist(furthest, goal)
            if d < best_dist:
                best_dist = d
                best = furthest
    return best


def bug2_old(start, goal, walkable, max_steps=5000):
    """bug2 with old find_detour_target (all perimeter cells)."""
    line_set = set()
    path = [start]
    current = start
    prev = None
    is_tracing = False
    obstacle_start_dist = 0
    tracing_dir = 0
    trace_left = True

    for _ in range(max_steps):
        if current == goal:
            break

        next_pos = None

        if not is_tracing:
            target = goal
            thin = create_thin_line(current, goal)
            vision = visible_from(current)
            for cell in thin[1:]:
                if cell not in vision:
                    break
                if cell not in walkable:
                    detour = find_detour_target_old(current, goal, walkable)
                    if detour is not None and dist(detour, goal) < dist(current, goal):
                        target = detour
                    break

            next_cell, blocked = step_along_line(current, target, walkable)
            if blocked is None and next_cell == prev:
                next_cell, blocked = step_along_line(current, goal, walkable)
            if blocked is not None:
                is_tracing = True
                obstacle_start_dist = dist(current, goal)
                tracing_dir = blocked
                line_set, _ = create_line(goal, current)
                vision = visible_from(current)
                left_steps, left_end = _simulate_trace(
                    current, blocked, True, walkable, vision)
                right_steps, right_end = _simulate_trace(
                    current, blocked, False, walkable, vision)
                sim_steps = min(left_steps, right_steps)
                if sim_steps > 0:
                    _, left_end = _simulate_trace(
                        current, blocked, True, walkable, vision, sim_steps)
                    _, right_end = _simulate_trace(
                        current, blocked, False, walkable, vision, sim_steps)
                    trace_left = dist(left_end, goal) <= dist(right_end, goal)
                else:
                    trace_left = True
            else:
                next_pos = next_cell
        else:
            lookahead = furthest_visible_on_line(current, goal, walkable)
            if lookahead is not None and dist(lookahead, goal) < obstacle_start_dist:
                is_tracing = False
                continue

            if can_move(current, tracing_dir, walkable):
                next_pos = move(current, tracing_dir)
                if trace_left:
                    tracing_dir = rotate_right(rotate_right(tracing_dir))
                else:
                    tracing_dir = rotate_left(rotate_left(tracing_dir))
            else:
                for _ in range(8):
                    if trace_left:
                        tracing_dir = rotate_left(tracing_dir)
                    else:
                        tracing_dir = rotate_right(tracing_dir)
                    if can_move(current, tracing_dir, walkable):
                        next_pos = move(current, tracing_dir)
                        if trace_left:
                            tracing_dir = rotate_right(rotate_right(tracing_dir))
                        else:
                            tracing_dir = rotate_left(rotate_left(tracing_dir))
                        break
                if next_pos is None:
                    return path, False

        if next_pos is not None:
            prev = current
            current = next_pos
            path.append(current)

    return path, current == goal


def run_comparison(map_path, num_trials=5000, seed=42):
    print(f"\n{'='*60}")
    print(f"Map: {map_path}  |  Trials: {num_trials}")
    print(f"{'='*60}")

    img, walkable, w, h = load_map(map_path)
    walkable_list = list(walkable)
    rng = random.Random(seed)

    pairs = []
    for _ in range(num_trials):
        start = rng.choice(walkable_list)
        goal = rng.choice(walkable_list)
        while goal == start:
            goal = rng.choice(walkable_list)
        pairs.append((start, goal))

    # Precompute dijkstra
    dij_results = {}
    for start, goal in pairs:
        dij_results[(start, goal)] = dijkstra(start, goal, walkable)

    old_wins = 0
    new_wins = 0
    ties = 0
    old_fails = 0
    new_fails = 0
    old_total_steps = 0
    new_total_steps = 0
    old_total_ratio = 0.0
    new_total_ratio = 0.0
    valid = 0

    t0 = time.time()
    for start, goal in pairs:
        old_path, old_reached = bug2_old(start, goal, walkable)
        if not old_reached:
            old_fails += 1
    old_time = time.time() - t0

    t0 = time.time()
    for start, goal in pairs:
        new_path, new_reached = bug2_new(start, goal, walkable)
        if not new_reached:
            new_fails += 1
    new_time = time.time() - t0

    # Reset for quality comparison
    old_fails = 0
    new_fails = 0
    for start, goal in pairs:
        d_path = dij_results[(start, goal)]
        if d_path is None:
            continue
        d_len = len(d_path) - 1
        if d_len == 0:
            continue

        old_path, old_reached = bug2_old(start, goal, walkable)
        new_path, new_reached = bug2_new(start, goal, walkable)
        old_len = len(old_path) - 1
        new_len = len(new_path) - 1

        if not old_reached:
            old_fails += 1
        if not new_reached:
            new_fails += 1

        if old_reached and new_reached:
            valid += 1
            old_total_steps += old_len
            new_total_steps += new_len
            old_total_ratio += old_len / d_len
            new_total_ratio += new_len / d_len
            if new_len < old_len:
                new_wins += 1
            elif old_len < new_len:
                old_wins += 1
            else:
                ties += 1

    print(f"\nResults (both reached goal): {valid} trials")
    print(f"  New (2-dir)    wins: {new_wins}")
    print(f"  Old (all-peri) wins: {old_wins}")
    print(f"  Ties:                {ties}")
    if valid > 0:
        print(f"\n  Avg steps (old): {old_total_steps / valid:.1f}")
        print(f"  Avg steps (new): {new_total_steps / valid:.1f}")
        print(f"  Avg ratio to Dijkstra (old): {old_total_ratio / valid:.2f}x")
        print(f"  Avg ratio to Dijkstra (new): {new_total_ratio / valid:.2f}x")
    print(f"\n  Failures (old): {old_fails}")
    print(f"  Failures (new): {new_fails}")
    print(f"\n  Time (old): {old_time:.2f}s")
    print(f"  Time (new): {new_time:.2f}s")
    print(f"  Speedup:    {old_time / new_time:.2f}x")


if __name__ == "__main__":
    maps = ["testmap1.png", "testmap2.png", "testmap3.png"]
    for m in maps:
        try:
            run_comparison(m, num_trials=5000)
        except Exception as e:
            print(f"  Skipped {m}: {e}")
