import heapq
import random

import matplotlib.pyplot as plt
from PIL import Image


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


def dijkstra(start, goal, walkable):
    NEIGHBORS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

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


def draw_path(img, path, start, goal):
    img = img.copy()
    pixels = img.load()

    for x, y in path:
        pixels[x, y] = (80, 120, 255, 255)
    pixels[start[0], start[1]] = (0, 200, 0, 255)
    pixels[goal[0], goal[1]] = (255, 0, 0, 255)

    return img


def main() -> None:
    img, walkable, w, h = load_map("testmap1.png")
    walkable_list = list(walkable)

    start = random.choice(walkable_list)
    goal = random.choice(walkable_list)
    while goal == start:
        goal = random.choice(walkable_list)

    print(f"Map size: {w}x{h}, walkable cells: {len(walkable)}")
    print(f"Start: {start}")
    print(f"Goal:  {goal}")

    path = dijkstra(start, goal, walkable)

    if path is None:
        print("No path found!")
        return

    print(f"Path length: {len(path) - 1} turns")

    result = draw_path(img, path, start, goal)

    fig, ax = plt.subplots()
    fig.set_facecolor("grey")
    ax.imshow(result)
    ax.axis("off")
    ax.set_title(f"Start {start} → Goal {goal} | {len(path) - 1} turns")
    plt.show()


if __name__ == "__main__":
    main()
