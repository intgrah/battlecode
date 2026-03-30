"""A/B benchmark: original HPA* vs optimised HPA*.

Runs both implementations on identical (map, seed, pairs) inputs,
collects per-query wall-clock times, and performs a paired Wilcoxon
signed-rank test per map and overall.  Reports at the 1% significance
level.

Usage:
    python -m scripts.bench_hpastar_ab [--pairs 200] [--seed 42] [--rounds 5]
"""

import argparse
import heapq
import importlib.util
import random
import sys
import time
import types
from pathlib import Path
from statistics import mean, median

# ---------------------------------------------------------------------------
# Stubs for cambc / util
# ---------------------------------------------------------------------------
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


_cambc.Environment = _Env  # type: ignore[attr-defined]
_cambc.Position = _Pos  # type: ignore[attr-defined]
sys.modules["cambc"] = _cambc

_util = types.ModuleType("util")
_util.Symmetry = type(  # type: ignore[attr-defined]
    "SymEnum",
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

from hardcode.known import KnownMap  # noqa: E402
from hardcode.map import DIMENSIONS, TILES, decode  # noqa: E402

# ---------------------------------------------------------------------------
# Load both HPA* versions
# ---------------------------------------------------------------------------


def _load_module(name: str, path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_old_mod = _load_module("hpastar_old", "/tmp/hpastar_old.py")
_new_mod = _load_module("hpastar_new", str(Path(_v50) / "algorithms" / "hpastar.py"))
GatewayGraphOld = _old_mod.GatewayGraph
GatewayGraphNew = _new_mod.GatewayGraph

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INF = 1_000_000
_COST_EMPTY = 10
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


# ---------------------------------------------------------------------------
# Validation & ground truth
# ---------------------------------------------------------------------------


def dijkstra_full(
    w: int, h: int, tiles: list[int], sx: int, sy: int
) -> list[int]:
    n = w * h
    dist = [_INF] * n
    si = sy * w + sx
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        cx, cy = node % w, node // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if tiles[ni] == 1:
                    continue
                c = _COST_EMPTY + (1 if dx != 0 and dy != 0 else 0)
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    heapq.heappush(heap, (nd, ni))
    return dist


def validate_path(
    w: int, h: int, tiles: list[int], path: list[int], sx: int, sy: int, gx: int, gy: int
) -> tuple[int, str | None]:
    if not path:
        return _INF, "empty"
    if path[0] != sy * w + sx:
        return _INF, "start"
    if path[-1] != gy * w + gx:
        return _INF, "goal"
    total = 0
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx > 1 or dy > 1:
            return _INF, f"non-adj {i}"
        if tiles[path[i + 1]] == 1:
            return _INF, f"wall {i}"
        total += _COST_EMPTY + (1 if dx != 0 and dy != 0 else 0)
    return total, None


# ---------------------------------------------------------------------------
# Wilcoxon signed-rank test (no scipy dependency)
# ---------------------------------------------------------------------------


def wilcoxon_signed_rank(x: list[float], y: list[float]) -> tuple[float, float]:
    """Two-sided Wilcoxon signed-rank test.  Returns (T_statistic, p_value).
    Uses normal approximation for n >= 10."""
    import math

    diffs = [a - b for a, b in zip(x, y) if a != b]
    n = len(diffs)
    if n < 10:
        return 0.0, 1.0  # too few samples

    ranked = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(diffs[ranked[j]]) == abs(diffs[ranked[i]]):
            j += 1
        avg_rank = (i + j + 1) / 2  # 1-based average
        for k in range(i, j):
            ranks[ranked[k]] = avg_rank
        i = j

    w_plus = sum(ranks[i] for i in range(n) if diffs[i] > 0)
    w_minus = sum(ranks[i] for i in range(n) if diffs[i] < 0)
    t_stat = min(w_plus, w_minus)

    # Normal approximation.
    mean_t = n * (n + 1) / 4
    var_t = n * (n + 1) * (2 * n + 1) / 24
    z = (t_stat - mean_t) / math.sqrt(var_t)
    # Two-sided p-value from z.
    p = 2 * _norm_cdf(z)
    return t_stat, p


def _norm_cdf(z: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun 26.2.17)."""
    import math

    if z > 6:
        return 1.0
    if z < -6:
        return 0.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if z >= 0 else -1
    x = abs(z) / math.sqrt(2)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


def tile_cost_fn(tiles: list[int], w: int):  # noqa: ANN201
    def cost(x: int, y: int) -> int:
        return _INF if tiles[y * w + x] == 1 else _COST_EMPTY
    return cost


def bench_map(
    km: KnownMap,
    n_pairs: int,
    rng_seed: int,
    n_rounds: int,
    cluster_size: int,
) -> dict:
    w, h = DIMENSIONS[km]
    n = w * h
    name = km.value

    env = decode(TILES[km](), n)
    tiles = [int(e) for e in env]
    passable = [(i % w, i // w) for i in range(n) if tiles[i] != 1]
    if len(passable) < 2:
        return {"map": name, "skip": True}

    cost_fn = tile_cost_fn(tiles, w)

    rng = random.Random(rng_seed)
    pairs: list[tuple[int, int, int, int]] = []
    for _ in range(n_pairs):
        a = rng.choice(passable)
        b = rng.choice(passable)
        pairs.append((a[0], a[1], b[0], b[1]))

    # Build both graphs.
    gg_old = GatewayGraphOld(w, h, cost_fn, cluster_size=cluster_size)
    gg_new = GatewayGraphNew(w, h, cost_fn, cluster_size=cluster_size)

    # Warm up.
    for sx, sy, gx, gy in pairs[:5]:
        gg_old.find_path(sx, sy, gx, gy)
        gg_new.find_path(sx, sy, gx, gy)

    # Collect per-query times over multiple rounds.
    old_times: list[float] = []
    new_times: list[float] = []
    new_invalid = 0
    new_wrong_cost = 0
    old_invalid = 0

    for _ in range(n_rounds):
        for sx, sy, gx, gy in pairs:
            t0 = time.perf_counter()
            path_old = gg_old.find_path(sx, sy, gx, gy)
            old_times.append((time.perf_counter() - t0) * 1e6)

            t0 = time.perf_counter()
            path_new = gg_new.find_path(sx, sy, gx, gy)
            new_times.append((time.perf_counter() - t0) * 1e6)

            # Validate new path.
            if path_new is not None:
                _, err = validate_path(w, h, tiles, path_new, sx, sy, gx, gy)
                if err is not None:
                    new_invalid += 1
            if path_old is not None:
                _, err = validate_path(w, h, tiles, path_old, sx, sy, gx, gy)
                if err is not None:
                    old_invalid += 1

            # Check reachability agreement.
            if (path_old is None) != (path_new is None):
                new_wrong_cost += 1

    # Statistics.
    t_stat, p_val = wilcoxon_signed_rank(old_times, new_times)
    old_median = median(old_times)
    new_median = median(new_times)
    old_max = max(old_times)
    new_max = max(new_times)
    old_p95 = sorted(old_times)[int(len(old_times) * 0.95)]
    new_p95 = sorted(new_times)[int(len(new_times) * 0.95)]
    speedup = old_median / new_median if new_median > 0 else 0
    sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""

    return {
        "map": name,
        "size": f"{w}x{h}",
        "n": len(old_times),
        "old_p50": round(old_median),
        "new_p50": round(new_median),
        "old_p95": round(old_p95),
        "new_p95": round(new_p95),
        "old_max": round(old_max),
        "new_max": round(new_max),
        "speedup": round(speedup, 3),
        "p_value": p_val,
        "sig": sig,
        "new_invalid": new_invalid,
        "old_invalid": old_invalid,
        "reachability_mismatch": new_wrong_cost,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rounds", type=int, default=5, help="Repeat each pair N times")
    parser.add_argument("--cluster-size", type=int, default=7)
    args = parser.parse_args()

    print(
        f"{'Map':<25} {'Size':>6} {'N':>5} "
        f"| {'Old p50':>8} {'New p50':>8} {'Speedup':>8} "
        f"| {'Old p95':>8} {'New p95':>8} "
        f"| {'Old max':>8} {'New max':>8} "
        f"| {'p-value':>10} {'Sig':>4} "
        f"| {'Inv':>4}",
    )
    print("=" * 140)

    all_results: list[dict] = []
    for km in KnownMap:
        r = bench_map(km, args.pairs, args.seed, args.rounds, args.cluster_size)
        if r.get("skip"):
            continue
        all_results.append(r)
        print(
            f"{r['map']:<25} {r['size']:>6} {r['n']:>5} "
            f"| {r['old_p50']:>7}u {r['new_p50']:>7}u {r['speedup']:>7.3f}x "
            f"| {r['old_p95']:>7}u {r['new_p95']:>7}u "
            f"| {r['old_max']:>7}u {r['new_max']:>7}u "
            f"| {r['p_value']:>10.2e} {r['sig']:>4} "
            f"| {r['new_invalid']:>4}",
        )

    print("=" * 140)

    # Overall.
    sig_improved = sum(1 for r in all_results if r["p_value"] < 0.01 and r["speedup"] > 1)
    sig_regressed = sum(1 for r in all_results if r["p_value"] < 0.01 and r["speedup"] < 1)
    tot_invalid = sum(r["new_invalid"] for r in all_results)
    tot_old_invalid = sum(r["old_invalid"] for r in all_results)
    avg_speedup = mean(r["speedup"] for r in all_results)
    max_old = max(r["old_max"] for r in all_results)
    max_new = max(r["new_max"] for r in all_results)

    print(f"Maps significantly faster  (p<0.01): {sig_improved}/{len(all_results)}")
    print(f"Maps significantly slower  (p<0.01): {sig_regressed}/{len(all_results)}")
    print(f"Average speedup (median ratio):       {avg_speedup:.3f}x")
    print(f"Max query time old:                   {max_old}us")
    print(f"Max query time new:                   {max_new}us")
    print(f"Total invalid paths (new):            {tot_invalid}")
    print(f"Total invalid paths (old):            {tot_old_invalid}")


if __name__ == "__main__":
    main()
