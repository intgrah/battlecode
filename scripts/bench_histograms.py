"""Generate raw per-query timing + optimality data for histogram plots.

Saves CSV with one row per (map, technique, query) triple.
Then generates matplotlib histograms.

Usage:
    python -m scripts.bench_histograms [--pairs 200] [--seed 42]
"""

import csv
import heapq
import random
import sys
import time
import types
from collections import deque
from pathlib import Path

_cambc = types.ModuleType("cambc")


class _Env:
    EMPTY = 0
    WALL = 1
    ORE_TITANIUM = 2
    ORE_AXIONITE = 3


class _Pos:
    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __eq__(self, o: object) -> bool:
        return isinstance(o, _Pos) and self.x == o.x and self.y == o.y

    def __hash__(self) -> int:
        return hash((self.x, self.y))


_cambc.Environment = _Env
_cambc.Position = _Pos
sys.modules["cambc"] = _cambc
_util = types.ModuleType("util")
_util.Symmetry = type(
    "S",
    (),
    {
        "ROT": type("S", (), {"name": "ROT"})(),
        "HOR": type("S", (), {"name": "HOR"})(),
        "VER": type("S", (), {"name": "VER"})(),
    },
)()
sys.modules["util"] = _util
_v50 = str(Path(__file__).resolve().parent.parent / "bots" / "intgrah" / "v50")
if _v50 not in sys.path:
    sys.path.insert(0, _v50)
from hardcode.known import KnownMap
from hardcode.map import DIMENSIONS, TILES, decode

_INF = 1_000_000
_COST_ROAD = 2
_COST_EMPTY = 10
_MAX_EDGE = 14
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def build_nb(w: int, h: int) -> list[list[tuple[int, bool]]]:
    n = w * h
    nb: list[list[tuple[int, bool]]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append((ny * w + nx, dx != 0 and dy != 0))
    return nb


def build_h(n: int, w: int, gi: int) -> list[int]:
    gx, gy = gi % w, gi // w
    h = [0] * n
    for i in range(n):
        dx = abs(i % w - gx)
        dy = abs(i // w - gy)
        h[i] = max(dy, dx) * _COST_ROAD
    return h


def val_path(cost: list[int], w: int, path: list[int], si: int, gi: int) -> int:
    if not path or path[0] != si or path[-1] != gi:
        return -1
    total = 0
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx > 1 or dy > 1:
            return -1
        c = cost[path[i + 1]]
        if c >= _INF:
            return -1
        if dx != 0 and dy != 0:
            c += 1
        total += c
    return total


def dijk_gt(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, si: int
) -> list[int]:
    dist = [_INF] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = d + c
            if nd < dist[ni]:
                dist[ni] = nd
                heapq.heappush(heap, (nd, ni))
    return dist


def extr(parent: list[int], si: int, gi: int) -> list[int] | None:
    if parent[gi] == -1 and gi != si:
        return None
    path: list[int] = []
    cur = gi
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def astar_heap(
    cost: list[int],
    nb: list[list[tuple[int, bool]]],
    n: int,
    si: int,
    gi: int,
    ht: list[int],
    g: list[int],
    p: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    g[si] = 0
    touched = [si]
    heap: list[tuple[int, int]] = [(ht[si], si)]
    result = None
    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            result = extr(p, si, gi)
            break
        if f > g[node] + ht[node]:
            continue
        gn = g[node]
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = gn + c
            if nd < g[ni]:
                if g[ni] == _INF:
                    touched.append(ni)
                g[ni] = nd
                p[ni] = node
                heapq.heappush(heap, (nd + ht[ni], ni))
    for ti in touched:
        g[ti] = _INF
        p[ti] = -1
    return result


def dial_ex(
    cost: list[int],
    nb: list[list[tuple[int, bool]]],
    n: int,
    si: int,
    gi: int,
    dist: list[int],
    p: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    dist[si] = 0
    touched = [si]
    bk: list[deque[int]] = [deque() for _ in range(_MAX_EDGE)]
    bk[0].append(si)
    cur = 0
    result = None
    emp = 0
    while emp < _MAX_EDGE:
        bi = cur % _MAX_EDGE
        if not bk[bi]:
            cur += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        if dist[node] != cur:
            continue
        if node == gi:
            result = extr(p, si, gi)
            break
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = cur + c
            if nd < dist[ni]:
                if dist[ni] == _INF:
                    touched.append(ni)
                dist[ni] = nd
                p[ni] = node
                bk[nd % _MAX_EDGE].append(ni)
    for ti in touched:
        dist[ti] = _INF
        p[ti] = -1
    return result


def w_astar(
    cost: list[int],
    nb: list[list[tuple[int, bool]]],
    n: int,
    si: int,
    gi: int,
    ht: list[int],
    g: list[int],
    p: list[int],
    w: int,
) -> list[int] | None:
    if si == gi:
        return [si]
    g[si] = 0
    touched = [si]
    heap: list[tuple[int, int]] = [(ht[si] * w, si)]
    result = None
    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            result = extr(p, si, gi)
            break
        if f > g[node] + ht[node] * w:
            continue
        gn = g[node]
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = gn + c
            if nd < g[ni]:
                if g[ni] == _INF:
                    touched.append(ni)
                g[ni] = nd
                p[ni] = node
                heapq.heappush(heap, (nd + ht[ni] * w, ni))
    for ti in touched:
        g[ti] = _INF
        p[ti] = -1
    return result


TECHNIQUES = ["dial_exact", "astar_heap", "weighted_3", "weighted_5"]


def run_tech(
    tech: str,
    cost: list[int],
    nb: list[list[tuple[int, bool]]],
    n: int,
    w: int,
    si: int,
    gi: int,
    ht: list[int],
    g: list[int],
    p: list[int],
    d: list[int],
) -> list[int] | None:
    if tech == "astar_heap":
        return astar_heap(cost, nb, n, si, gi, ht, g, p)
    if tech == "dial_exact":
        return dial_ex(cost, nb, n, si, gi, d, p)
    if tech.startswith("weighted_"):
        return w_astar(cost, nb, n, si, gi, ht, g, p, int(tech.split("_")[1]))
    return None


def _place_roads(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, rng: random.Random,
    passable: list[int], n_paths: int,
) -> None:
    for _ in range(n_paths):
        si = rng.choice(passable)
        gi = rng.choice(passable)
        if si == gi:
            continue
        dist = dijk_gt(cost, nb, n, si)
        if dist[gi] >= _INF:
            continue
        parent = [-1] * n
        parent[si] = si
        heap: list[tuple[int, int]] = [(0, si)]
        d_arr = [_INF] * n
        d_arr[si] = 0
        while heap:
            d, node = heapq.heappop(heap)
            if d > d_arr[node]:
                continue
            if node == gi:
                break
            for ni, diag in nb[node]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < d_arr[ni]:
                    d_arr[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        cur = gi
        while cur != si and cur != -1:
            if cost[cur] == _COST_EMPTY:
                cost[cur] = _COST_ROAD
            cur = parent[cur]


def bench_map(km: KnownMap, seed: int, n_pairs: int) -> list[dict]:
    w, h = DIMENSIONS[km]
    n = w * h
    env = decode(TILES[km](), n)
    tt = [int(e) for e in env]
    cost = [_INF if tt[i] in (1, 2, 3) else _COST_EMPTY for i in range(n)]
    nb = build_nb(w, h)
    ps = [i for i in range(n) if cost[i] < _INF]
    rng = random.Random(seed)
    _place_roads(cost, nb, n, rng, ps, n_paths=10)
    n_roads = sum(1 for c in cost if c == _COST_ROAD)
    pairs = [(rng.choice(ps), rng.choice(ps)) for _ in range(n_pairs)]
    gt_cache: dict[int, list[int]] = {}
    g = [_INF] * n
    p = [-1] * n
    d = [_INF] * n
    rows: list[dict] = []
    for tech in TECHNIQUES:
        for si, gi in pairs:
            if si == gi:
                continue
            if si not in gt_cache:
                gt_cache[si] = dijk_gt(cost, nb, n, si)
            gd = gt_cache[si][gi]
            if gd >= _INF:
                continue
            ht = build_h(n, w, gi)
            t0 = time.perf_counter()
            path = run_tech(tech, cost, nb, n, w, si, gi, ht, g, p, d)
            elapsed = (time.perf_counter() - t0) * 1e6
            opt = 0.0
            if path and path[-1] == gi:
                pc = val_path(cost, w, path, si, gi)
                if pc > 0 and gd > 0:
                    opt = pc / gd
            rows.append(
                {
                    "map": km.value,
                    "tech": tech,
                    "time_us": round(elapsed, 1),
                    "optimality": round(opt, 4),
                    "optimal_cost": gd,
                    "n_roads": n_roads,
                }
            )
    return rows


def plot(csv_path: Path) -> None:
    import matplotlib.pyplot as plt

    data: dict[str, list[dict]] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            tech = row["tech"]
            data.setdefault(tech, []).append(row)

    techs = TECHNIQUES
    n_techs = len(techs)

    fig, axes = plt.subplots(2, n_techs, figsize=(5 * n_techs, 8), squeeze=False)
    fig.suptitle("Pathfinding Benchmark: Per-Query Distributions (all 38 maps)", fontsize=14)

    for col, tech in enumerate(techs):
        rows = data.get(tech, [])
        times = [float(r["time_us"]) for r in rows]
        opts = [float(r["optimality"]) for r in rows if float(r["optimality"]) > 0]

        ax_t = axes[0][col]
        if times:
            ax_t.hist(times, bins=80, color="steelblue", edgecolor="none", alpha=0.8)
            ax_t.axvline(2000, color="red", linestyle="--", linewidth=1, label="2ms budget")
            over = sum(1 for t in times if t > 2000)
            total = len(times)
            p50 = sorted(times)[total // 2]
            p99 = sorted(times)[int(total * 0.99)]
            ax_t.set_title(f"{tech}\np50={p50:.0f}us  p99={p99:.0f}us  max={max(times):.0f}us\n>{'{'}2ms: {over}/{total}", fontsize=9)
            ax_t.legend(fontsize=7)
        ax_t.set_xlabel("Time (us)")
        ax_t.set_ylabel("Count")

        ax_o = axes[1][col]
        if opts:
            ax_o.hist(opts, bins=80, color="darkorange", edgecolor="none", alpha=0.8)
            ax_o.axvline(1.0, color="green", linestyle="--", linewidth=1, label="optimal")
            mean_o = sum(opts) / len(opts)
            max_o = max(opts)
            p95_o = sorted(opts)[int(len(opts) * 0.95)]
            ax_o.set_title(f"mean={mean_o:.3f}x  p95={p95_o:.3f}x  max={max_o:.3f}x", fontsize=9)
            ax_o.legend(fontsize=7)
        ax_o.set_xlabel("Optimality ratio (path / optimal)")
        ax_o.set_ylabel("Count")

    plt.tight_layout()
    out = csv_path.with_suffix(".png")
    fig.savefig(out, dpi=150)
    print(f"Wrote {out}", file=sys.stderr)
    plt.close(fig)

    all_maps = sorted({r["map"] for tech_rows in data.values() for r in tech_rows})
    map_times: dict[str, dict[str, list[float]]] = {m: {} for m in all_maps}
    map_opts: dict[str, dict[str, list[float]]] = {m: {} for m in all_maps}
    for tech in techs:
        for r in data.get(tech, []):
            m = r["map"]
            map_times[m].setdefault(tech, []).append(float(r["time_us"]))
            o = float(r["optimality"])
            if o > 0:
                map_opts[m].setdefault(tech, []).append(o)

    median_max = {}
    for m in all_maps:
        vals = []
        for tech in techs:
            ts = map_times[m].get(tech, [])
            if ts:
                vals.append(sorted(ts)[len(ts) // 2])
        median_max[m] = max(vals) if vals else 0
    maps_sorted = sorted(all_maps, key=lambda m: median_max[m], reverse=True)
    n_maps = len(maps_sorted)

    fig2, axes2 = plt.subplots(1, n_techs, figsize=(5 * n_techs, max(8, n_maps * 0.28)), squeeze=False)
    fig2.suptitle("Per-Map Query Time (box: IQR, whiskers: min/max)", fontsize=14, y=0.995)

    for col, tech in enumerate(techs):
        ax = axes2[0][col]
        bp_data = []
        labels = []
        for m in maps_sorted:
            ts = map_times[m].get(tech, [])
            bp_data.append(ts if ts else [0])
            labels.append(m[:18])

        bp = ax.boxplot(
            bp_data,
            vert=False,
            positions=range(n_maps),
            widths=0.6,
            patch_artist=True,
            whis=(0, 100),
            showfliers=False,
            medianprops={"color": "black", "linewidth": 1.2},
            boxprops={"facecolor": "steelblue", "alpha": 0.7, "edgecolor": "steelblue"},
            whiskerprops={"color": "steelblue", "linewidth": 0.8},
            capprops={"color": "steelblue", "linewidth": 0.8},
        )
        for i, box in enumerate(bp["boxes"]):
            whisker_r = bp["whiskers"][i * 2 + 1]
            xmax = max(whisker_r.get_xdata())
            if xmax > 2000:
                box.set_facecolor("salmon")
                box.set_edgecolor("red")

        ax.axvline(2000, color="red", linestyle="--", linewidth=1, label="2ms budget")
        ax.set_yticks(range(n_maps))
        ax.set_yticklabels(labels, fontsize=6)
        ax.set_xlabel("Query time (us)")
        ax.set_title(tech, fontsize=10)
        ax.invert_yaxis()
        ax.legend(fontsize=7, loc="lower right")

    plt.tight_layout()
    out2 = csv_path.with_name(csv_path.stem + "_per_map.png")
    fig2.savefig(out2, dpi=150)
    print(f"Wrote {out2}", file=sys.stderr)
    plt.close(fig2)

    fig3, axes3 = plt.subplots(1, n_techs, figsize=(5 * n_techs, max(8, n_maps * 0.28)), squeeze=False)
    fig3.suptitle("Per-Map Optimality Ratio (box: IQR, whiskers: min/max)", fontsize=14, y=0.995)

    for col, tech in enumerate(techs):
        ax = axes3[0][col]
        bp_data = []
        labels = []
        for m in maps_sorted:
            os = map_opts[m].get(tech, [])
            bp_data.append(os if os else [1.0])
            labels.append(m[:18])

        bp = ax.boxplot(
            bp_data,
            vert=False,
            positions=range(n_maps),
            widths=0.6,
            patch_artist=True,
            whis=(0, 100),
            showfliers=False,
            medianprops={"color": "black", "linewidth": 1.2},
            boxprops={"facecolor": "darkorange", "alpha": 0.7, "edgecolor": "darkorange"},
            whiskerprops={"color": "darkorange", "linewidth": 0.8},
            capprops={"color": "darkorange", "linewidth": 0.8},
        )

        ax.axvline(1.0, color="green", linestyle="--", linewidth=1, label="optimal")
        ax.set_yticks(range(n_maps))
        ax.set_yticklabels(labels, fontsize=6)
        ax.set_xlabel("Optimality ratio (path / optimal)")
        ax.set_title(tech, fontsize=10)
        ax.invert_yaxis()
        ax.legend(fontsize=7, loc="lower right")

    plt.tight_layout()
    out3 = csv_path.with_name(csv_path.stem + "_per_map_opt.png")
    fig3.savefig(out3, dpi=150)
    print(f"Wrote {out3}", file=sys.stderr)
    plt.close(fig3)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--plot-only", action="store_true")
    args = parser.parse_args()

    csv_path = Path(__file__).resolve().parent / "bench_histograms.csv"

    if not args.plot_only:
        all_rows: list[dict] = []
        for km in KnownMap:
            print(f"  {km.value}...", file=sys.stderr, flush=True)
            all_rows.extend(bench_map(km, args.seed, args.pairs))
        fns = list(all_rows[0].keys())
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fns)
            w.writeheader()
            w.writerows(all_rows)
        print(f"Wrote {csv_path} ({len(all_rows)} rows)", file=sys.stderr)

    plot(csv_path)


if __name__ == "__main__":
    main()
