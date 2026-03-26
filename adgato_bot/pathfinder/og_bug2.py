import heapq
import math
import random
import matplotlib.pyplot as plt
from PIL import Image


NEIGHBORS = [(-1, -1), (0, -1), (1, -1),
             (-1,  0),          (1,  0),
             (-1,  1), (0,  1), (1,  1)]


def load_map(path):
    img = Image.open(path).convert("RGBA")
    pixels = img.load()
    w, h = img.size
    walkable = set()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
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


def get_visible(pos, walkable):
    """Return the set of walkable cells visible from pos."""
    x, y = pos
    return {(x + dx, y + dy) for dx, dy in VISION_OFFSETS
            if (x + dx, y + dy) in walkable}


def dist_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def create_line(a, b):
    """Create a thick line of cells from a to b (Battlecode-style)."""
    locs = set()
    x, y = a
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    sx = 1 if dx > 0 else -1 if dx < 0 else 0
    sy = 1 if dy > 0 else -1 if dy < 0 else 0
    dx = abs(dx)
    dy = abs(dy)
    d = max(dx, dy)
    r = d // 2

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

    locs.add(b)
    return locs


# 8 directions in clockwise order
DIRS = [(0, -1), (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0), (-1, -1)]

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


def rotate_left(dir_idx):
    return (dir_idx - 1) % 8


def rotate_right(dir_idx):
    return (dir_idx + 1) % 8


def bug2(start, goal, walkable, max_steps=5000):
    """Bug2 pathfinding (Battlecode-style)."""
    line = set()
    path = [start]
    current = start
    is_tracing = False
    obstacle_start_dist = 0
    tracing_dir = 0

    for _ in range(max_steps):
        if current == goal:
            break

        if not is_tracing:
            dir_idx = direction_to(current, goal)
            if can_move(current, dir_idx, walkable):
                current = move(current, dir_idx)
                path.append(current)
            else:
                is_tracing = True
                obstacle_start_dist = dist_sq(current, goal)
                tracing_dir = dir_idx
                line = create_line(goal, current)
        else:
            if current in line and dist_sq(current, goal) < obstacle_start_dist:
                is_tracing = False
            else:
                if can_move(current, tracing_dir, walkable):
                    current = move(current, tracing_dir)
                    path.append(current)
                    tracing_dir = rotate_right(rotate_right(tracing_dir))
                else:
                    moved = False
                    for _ in range(8):
                        tracing_dir = rotate_left(tracing_dir)
                        if can_move(current, tracing_dir, walkable):
                            current = move(current, tracing_dir)
                            path.append(current)
                            tracing_dir = rotate_right(rotate_right(tracing_dir))
                            moved = True
                            break
                    if not moved:
                        return path, False

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


def main():
    img, walkable, w, h = load_map("testmap1.png")
    walkable_list = list(walkable)

    start = random.choice(walkable_list)
    goal = random.choice(walkable_list)
    while goal == start:
        goal = random.choice(walkable_list)

    print(f"Map size: {w}x{h}, walkable cells: {len(walkable)}")
    print(f"Start: {start}")
    print(f"Goal:  {goal}")

    d_path = dijkstra(start, goal, walkable)
    if d_path is None:
        print("No Dijkstra path found!")
        return
    print(f"Dijkstra: {len(d_path) - 1} turns")

    b_path, reached = bug2(start, goal, walkable)
    if reached:
        print(f"Bug2:     {len(b_path) - 1} turns")
    else:
        print(f"Bug2:     failed to reach goal ({len(b_path) - 1} steps taken)")

    result = draw_paths(img, d_path, b_path, start, goal)

    fig, ax = plt.subplots()
    fig.set_facecolor("grey")
    ax.imshow(result)
    ax.axis("off")
    d_label = f"Dijkstra(blue): {len(d_path) - 1}"
    b_label = f"Bug2(magenta): {len(b_path) - 1}{'' if reached else ' (failed)'}"
    ax.set_title(f"Start {start} → Goal {goal}\n{d_label} | {b_label}")
    plt.show()


if __name__ == "__main__":
    main()
