"""Run bug2 on a specific case and generate debug frames in frames/."""

from bug2 import bug2, dijkstra, load_map

img, walkable, w, h = load_map("testmap3.png")
s, g = (8, 7), (12, 16)

d_path = dijkstra(s, g, walkable)
if d_path:
    print(f"Dijkstra: {len(d_path) - 1} steps")

path, reached = bug2(s, g, walkable, debug_img=(img, w, h))
print(f"Bug2: {len(path) - 1} steps, reached={reached}")

import os

frames = sorted(os.listdir("frames"))
print(f"Generated {len(frames)} frames in frames/")
