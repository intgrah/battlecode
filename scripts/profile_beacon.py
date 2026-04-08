"""Line-profile beacon SSSP on all maps."""
from __future__ import annotations

import random
from pathlib import Path

from line_profiler import LineProfiler

from scripts.bench_nav import MapData, sssp_dijkstra_bucket_noparent_beacon

MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"

lp = LineProfiler()
lp.add_function(sssp_dijkstra_bucket_noparent_beacon)
wrapped = lp(sssp_dijkstra_bucket_noparent_beacon)

rng = random.Random(42)
for map_file in sorted(MAPS_DIR.glob("*.map26")):
    md = MapData(map_file)
    md.reset_cost_no_roads()
    md.place_roads()
    sources = [rng.choice(md.passable) for _ in range(200)]
    for s in sources:
        wrapped(md, s)

lp.print_stats()
