"""Benchmark HPA* pathfinding against A* baseline.

Usage:
    python -m scripts.bench_hpastar [--pairs 200] [--seed 42] [--timeout-ms 5]
"""

import argparse
import heapq
import random
import sys
import time
import types
from pathlib import Path
from statistics import mean

# ---------------------------------------------------------------------------
# Stub cambc/util so we can import hardcode.map
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

import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "hpastar",
    Path(_v50) / "algorithms" / "hpastar.py",
)
_hpamod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_hpamod)  # type: ignore[union-attr]
GatewayGraph = _hpamod.GatewayGraph
from hardcode.known import KnownMap  # noqa: E402
from hardcode.map import DIMENSIONS, TILES, decode  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INF = 1_000_000
_COST_EMPTY = 10
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


# ---------------------------------------------------------------------------
# Baseline: full Dijkstra (ground truth) and A* with Chebyshev
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


def astar_chebyshev(
    w: int, h: int, tiles: list[int], sx: int, sy: int, gx: int, gy: int
) -> tuple[int, int]:
    """Returns (cost, expansions)."""
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return 0, 0
    g: dict[int, int] = {si: 0}
    heap: list[tuple[int, int, int]] = [
        (max(abs(sx - gx), abs(sy - gy)) * _COST_EMPTY, 0, si)
    ]
    expanded = 0
    while heap:
        f, _, node = heapq.heappop(heap)
        if (
            f
            > g.get(node, _INF)
            + max(abs(node % w - gx), abs(node // w - gy)) * _COST_EMPTY
        ):
            continue
        if node == gi:
            return g[node], expanded
        expanded += 1
        cx, cy = node % w, node // w
        gn = g[node]
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if tiles[ni] == 1:
                    continue
                c = _COST_EMPTY + (1 if dx != 0 and dy != 0 else 0)
                nd = gn + c
                if nd < g.get(ni, _INF):
                    g[ni] = nd
                    h_val = max(abs(nx - gx), abs(ny - gy)) * _COST_EMPTY
                    heapq.heappush(heap, (nd + h_val, h_val, ni))
    return _INF, expanded


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def validate_path(
    w: int,
    h: int,
    tiles: list[int],
    path: list[int],
    sx: int,
    sy: int,
    gx: int,
    gy: int,
) -> tuple[int, str | None]:
    if not path:
        return _INF, "empty path"
    if path[0] != sy * w + sx:
        return _INF, f"start mismatch: path[0]={path[0]} expected {sy * w + sx}"
    if path[-1] != gy * w + gx:
        return _INF, f"goal mismatch: path[-1]={path[-1]} expected {gy * w + gx}"
    total = 0
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx > 1 or dy > 1:
            return _INF, f"non-adjacent step {i}: ({x0},{y0})->({x1},{y1})"
        if not (0 <= x1 < w and 0 <= y1 < h):
            return _INF, f"out of bounds step {i}: ({x1},{y1})"
        if tiles[path[i + 1]] == 1:
            return _INF, f"wall step {i}: ({x1},{y1})"
        c = _COST_EMPTY + (1 if dx != 0 and dy != 0 else 0)
        total += c
    return total, None


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------


def percentiles(
    data: list[float],
    ps: tuple[float, ...] = (0.50, 0.95, 0.99, 1.0),
) -> dict[str, float]:
    if not data:
        return {f"p{p:.2f}": 0.0 for p in ps}
    s = sorted(data)
    n = len(s)
    result: dict[str, float] = {}
    for p in ps:
        if p >= 1.0:
            result["max"] = s[-1]
        else:
            idx = p * (n - 1)
            lo = int(idx)
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            result[f"p{p:.2f}"] = s[lo] * (1 - frac) + s[hi] * frac
    return result


# ---------------------------------------------------------------------------
# Benchmark one map
# ---------------------------------------------------------------------------


def tile_cost_fn(tiles: list[int], w: int):  # noqa: ANN201
    def cost(x: int, y: int) -> int:
        if tiles[y * w + x] == 1:
            return _INF
        return _COST_EMPTY

    return cost


def bench_map(
    km: KnownMap,
    n_pairs: int,
    rng_seed: int,
    timeout_us: float,
    cluster_size: int,
) -> dict | None:
    w, h = DIMENSIONS[km]
    n = w * h
    name = km.value

    env = decode(TILES[km](), n)
    tiles = [int(e) for e in env]

    passable = [(i % w, i // w) for i in range(n) if tiles[i] != 1]
    if len(passable) < 2:
        return None

    cost_fn = tile_cost_fn(tiles, w)

    rng = random.Random(rng_seed)
    pairs: list[tuple[int, int, int, int]] = []
    for _ in range(n_pairs):
        a = rng.choice(passable)
        b = rng.choice(passable)
        pairs.append((a[0], a[1], b[0], b[1]))

    # Precompute
    t0 = time.perf_counter()
    gg = GatewayGraph(w, h, cost_fn, cluster_size=cluster_size)
    precompute_ms = (time.perf_counter() - t0) * 1000
    n_gw = len(gg._gw_tile)  # noqa: SLF001

    hpa_times: list[float] = []
    bl_times: list[float] = []
    opt_ratios: list[float] = []
    false_neg = 0
    false_pos = 0
    invalid_paths = 0
    tles = 0
    total_tested = 0

    for sx, sy, gx, gy in pairs:
        # Ground truth
        optimal_dist = dijkstra_full(w, h, tiles, sx, sy)
        gi = gy * w + gx
        optimal = optimal_dist[gi]

        # Baseline A*
        t0 = time.perf_counter()
        bl_cost, _ = astar_chebyshev(w, h, tiles, sx, sy, gx, gy)
        bl_times.append((time.perf_counter() - t0) * 1e6)

        # HPA*
        t0 = time.perf_counter()
        path = gg.find_path(sx, sy, gx, gy)
        elapsed = (time.perf_counter() - t0) * 1e6
        hpa_times.append(elapsed)

        if elapsed > timeout_us:
            tles += 1

        total_tested += 1
        is_reachable = optimal < _INF
        found = path is not None

        if is_reachable and not found:
            false_neg += 1
            print(
                f"  FALSE NEG {name} ({sx},{sy})->({gx},{gy})",
                file=sys.stderr,
            )
        elif not is_reachable and found:
            false_pos += 1
            print(
                f"  FALSE POS {name} ({sx},{sy})->({gx},{gy})",
                file=sys.stderr,
            )

        if found:
            hpa_cost, err = validate_path(w, h, tiles, path, sx, sy, gx, gy)
            if err is not None:
                invalid_paths += 1
                print(
                    f"  INVALID {name} ({sx},{sy})->({gx},{gy}): {err}",
                    file=sys.stderr,
                )
            elif is_reachable and optimal > 0:
                opt_ratios.append(hpa_cost / optimal)

    hpa_p = percentiles(hpa_times)
    bl_p = percentiles(bl_times)

    return {
        "map": name,
        "size": f"{w}x{h}",
        "passable": len(passable),
        "gateways": n_gw,
        "precompute_ms": round(precompute_ms, 1),
        "pairs": total_tested,
        "false_neg": false_neg,
        "false_pos": false_pos,
        "invalid": invalid_paths,
        "tles": tles,
        "opt_mean": round(mean(opt_ratios), 4) if opt_ratios else 0,
        "opt_worst": round(max(opt_ratios), 4) if opt_ratios else 0,
        "hpa_p50_us": round(hpa_p["p0.50"], 0),
        "hpa_p95_us": round(hpa_p["p0.95"], 0),
        "hpa_p99_us": round(hpa_p["p0.99"], 0),
        "hpa_max_us": round(hpa_p["max"], 0),
        "bl_p50_us": round(bl_p["p0.50"], 0),
        "bl_p95_us": round(bl_p["p0.95"], 0),
        "bl_max_us": round(bl_p["max"], 0),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark HPA* pathfinding")
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-us", type=float, default=2000)
    parser.add_argument("--cluster-size", type=int, default=7)
    args = parser.parse_args()

    print(
        f"{'Map':<25} {'Size':>6} {'Pass':>5} {'GW':>4} {'Pre':>6} "
        f"| {'FN':>3} {'FP':>3} {'Inv':>4} {'TLE':>4} "
        f"| {'OptMean':>8} {'OptWorst':>9} "
        f"| {'HPA p50':>8} {'p95':>8} {'p99':>8} {'max':>8} "
        f"| {'BL p50':>8} {'p95':>8} {'max':>8}",
    )
    print("=" * 160)

    totals: dict[str, list] = {
        "false_neg": [],
        "false_pos": [],
        "invalid": [],
        "tles": [],
        "opt_ratios": [],
        "hpa_max": [],
    }

    for km in KnownMap:
        r = bench_map(km, args.pairs, args.seed, args.timeout_us, args.cluster_size)
        if r is None:
            continue
        totals["false_neg"].append(r["false_neg"])
        totals["false_pos"].append(r["false_pos"])
        totals["invalid"].append(r["invalid"])
        totals["tles"].append(r["tles"])
        if r["opt_worst"] > 0:
            totals["opt_ratios"].append(r["opt_worst"])
        totals["hpa_max"].append(r["hpa_max_us"])

        print(
            f"{r['map']:<25} {r['size']:>6} {r['passable']:>5} {r['gateways']:>4} {r['precompute_ms']:>5.0f}ms"
            f" | {r['false_neg']:>3} {r['false_pos']:>3} {r['invalid']:>4} {r['tles']:>4}"
            f" | {r['opt_mean']:>8.4f} {r['opt_worst']:>9.4f}"
            f" | {r['hpa_p50_us']:>7.0f}u {r['hpa_p95_us']:>7.0f}u {r['hpa_p99_us']:>7.0f}u {r['hpa_max_us']:>7.0f}u"
            f" | {r['bl_p50_us']:>7.0f}u {r['bl_p95_us']:>7.0f}u {r['bl_max_us']:>7.0f}u",
        )

    print("=" * 160)
    print(
        f"TOTALS: false_neg={sum(totals['false_neg'])} false_pos={sum(totals['false_pos'])} "
        f"invalid={sum(totals['invalid'])} tles={sum(totals['tles'])} "
        f"worst_opt={max(totals['opt_ratios']):.4f} "
        f"worst_hpa_max_us={max(totals['hpa_max']):.0f}",
    )


if __name__ == "__main__":
    main()
