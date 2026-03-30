"""Benchmark landmark heuristics vs Manhattan, Chebyshev, and full APSP for A*.

Usage:
    python -m scripts.bench_landmarks [--pairs 200] [--seed 42] [--timeout-ms 5]

Outputs a CSV to stdout suitable for spreadsheet import.
"""

import argparse
import csv
import heapq
import random
import sys
import time
import types
from collections import deque
from pathlib import Path

# ---------------------------------------------------------------------------
# Stub cambc so we can import hardcode.map
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


class _Sym:
    ROT = type("S", (), {"name": "ROT"})()
    HOR = type("S", (), {"name": "HOR"})()
    VER = type("S", (), {"name": "VER"})()


_util.Symmetry = _Sym  # type: ignore[attr-defined]
sys.modules["util"] = _util

_v50 = str(Path(__file__).resolve().parent.parent / "bots" / "intgrah" / "v50")
if _v50 not in sys.path:
    sys.path.insert(0, _v50)

from hardcode.known import KnownMap  # noqa: E402
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INF = 1_000_000
_COST_EMPTY = 10
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
K_VALUES = (4, 8, 12, 16, 24, 32, 64)


# ---------------------------------------------------------------------------
# BFS (unweighted chebyshev, for APSP / landmark precomputation)
# ---------------------------------------------------------------------------


def bfs(
    n: int, passable_mask: bytearray, neighbors: list[list[int]], start: int
) -> bytearray:
    dist = bytearray(b"\xff" * n)
    dist[start] = 0
    q = deque([start])
    while q:
        ci = q.popleft()
        nd = dist[ci] + 1
        if nd >= 255:
            continue
        for ni in neighbors[ci]:
            if passable_mask[ni] and dist[ni] == 0xFF:
                dist[ni] = nd
                q.append(ni)
    return dist


def build_neighbors(w: int, h: int) -> list[list[int]]:
    n = w * h
    neighbors: list[list[int]] = []
    for i in range(n):
        cx, cy = i % w, i // w
        nb: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    nb.append(ny * w + nx)
        neighbors.append(nb)
    return neighbors


# ---------------------------------------------------------------------------
# Full APSP
# ---------------------------------------------------------------------------


def compute_apsp(
    w: int, h: int, passable_mask: bytearray, neighbors: list[list[int]]
) -> list[bytearray]:
    n = w * h
    return [bfs(n, passable_mask, neighbors, i) for i in range(n)]


# ---------------------------------------------------------------------------
# Landmark selection & table
# ---------------------------------------------------------------------------


def select_landmarks(
    w: int,
    h: int,
    passable_mask: bytearray,
    neighbors: list[list[int]],
    k: int,
    core_a: int,
    core_b: int,
) -> list[int]:
    """Farthest-point selection, seeded with both cores."""
    n = w * h
    landmarks: list[int] = []
    for c in (core_a, core_b):
        if passable_mask[c] and c not in landmarks:
            landmarks.append(c)

    min_dist = bytearray(b"\xff" * n)
    for lm in landmarks:
        d = bfs(n, passable_mask, neighbors, lm)
        for i in range(n):
            if d[i] < min_dist[i]:
                min_dist[i] = d[i]

    while len(landmarks) < k:
        best_i = -1
        best_d = -1
        for i in range(n):
            if passable_mask[i] and min_dist[i] != 0xFF and min_dist[i] > best_d:
                best_d = min_dist[i]
                best_i = i
        if best_i == -1:
            break
        landmarks.append(best_i)
        d = bfs(n, passable_mask, neighbors, best_i)
        for i in range(n):
            if d[i] < min_dist[i]:
                min_dist[i] = d[i]

    return landmarks


def build_landmark_table(
    n: int,
    passable_mask: bytearray,
    neighbors: list[list[int]],
    landmarks: list[int],
) -> list[bytearray]:
    return [bfs(n, passable_mask, neighbors, lm) for lm in landmarks]


# ---------------------------------------------------------------------------
# Heuristic functions (return weighted cost estimate)
# ---------------------------------------------------------------------------


def h_manhattan(node: int, goal: int, w: int) -> int:
    x0, y0 = node % w, node // w
    x1, y1 = goal % w, goal // w
    return (abs(x0 - x1) + abs(y0 - y1)) * _COST_EMPTY


def h_chebyshev(node: int, goal: int, w: int) -> int:
    x0, y0 = node % w, node // w
    x1, y1 = goal % w, goal // w
    return max(abs(x0 - x1), abs(y0 - y1)) * _COST_EMPTY


def h_landmark(node: int, goal: int, table: list[bytearray]) -> int:
    best = 0
    for d in table:
        dn = d[node]
        dg = d[goal]
        if dn == 0xFF or dg == 0xFF:
            continue
        diff = dn - dg if dn > dg else dg - dn
        if diff > best:
            best = diff
    return best * _COST_EMPTY


def h_apsp(node: int, goal: int, apsp: list[bytearray]) -> int:
    d = apsp[node][goal]
    return d * _COST_EMPTY if d < 255 else _INF


# ---------------------------------------------------------------------------
# A* with timeout
# ---------------------------------------------------------------------------


def astar(
    w: int,
    h: int,
    tiles: list[int],
    si: int,
    gi: int,
    hfunc,  # noqa: ANN001
    timeout_ns: int,
) -> tuple[int, int, bool]:
    """Returns (cost, expansions, timed_out)."""
    if si == gi:
        return 0, 0, False

    g: dict[int, int] = {si: 0}
    heap: list[tuple[int, int, int]] = [(hfunc(si), 0, si)]
    expanded = 0
    t_start = time.monotonic_ns()

    while heap:
        f, _, node = heapq.heappop(heap)
        g_node = g.get(node, _INF)
        if f > g_node + hfunc(node):
            continue
        if node == gi:
            return g_node, expanded, False
        expanded += 1
        if expanded & 63 == 0:
            if time.monotonic_ns() - t_start > timeout_ns:
                return _INF, expanded, True
        cx, cy = node % w, node // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if tiles[ni] == 1:  # WALL
                    continue
                c = _COST_EMPTY + (1 if dx != 0 and dy != 0 else 0)
                nd = g_node + c
                if nd < g.get(ni, _INF):
                    g[ni] = nd
                    hv = hfunc(ni)
                    heapq.heappush(heap, (nd + hv, hv, ni))

    return _INF, expanded, False


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------


def percentiles(
    data: list[float],
    ps: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75, 0.95, 1.0),
) -> list[tuple[str, float]]:
    if not data:
        return [(f"p{p:.2f}", 0.0) for p in ps]
    s = sorted(data)
    n = len(s)
    result: list[tuple[str, float]] = []
    for p in ps:
        if p >= 1.0:
            result.append(("p1.00", s[-1]))
        else:
            idx = p * (n - 1)
            lo = int(idx)
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            result.append((f"p{p:.2f}", s[lo] * (1 - frac) + s[hi] * frac))
    return result


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------


def bench_map(
    km: KnownMap,
    n_pairs: int,
    rng_seed: int,
    timeout_ms: float,
) -> list[dict]:
    w, h = DIMENSIONS[km]
    n = w * h
    name = km.value

    # Decode tiles: 0=EMPTY, 1=WALL, 2=ORE_TI, 3=ORE_AX
    env = decode(TILES[km](), n)
    tiles = [int(e) for e in env]

    passable_mask = bytearray(n)
    passable_list: list[int] = []
    for i in range(n):
        if tiles[i] != 1:
            passable_mask[i] = 1
            passable_list.append(i)

    n_passable = len(passable_list)
    if n_passable < 2:
        return []

    neighbors = build_neighbors(w, h)

    ca = CORE_A[km]
    cb = CORE_B[km]
    core_a_i = ca.y * w + ca.x
    core_b_i = cb.y * w + cb.x

    # Sample pairs
    rng = random.Random(rng_seed)
    pairs: list[tuple[int, int]] = []
    for _ in range(n_pairs):
        a = rng.choice(passable_list)
        b = rng.choice(passable_list)
        pairs.append((a, b))

    timeout_ns = int(timeout_ms * 1_000_000)

    # Precompute APSP
    print(f"  {name} ({w}x{h}, {n_passable} passable): APSP...", end="", file=sys.stderr, flush=True)
    t0 = time.perf_counter()
    apsp = compute_apsp(w, h, passable_mask, neighbors)
    apsp_ms = (time.perf_counter() - t0) * 1000
    print(f" {apsp_ms:.0f}ms", file=sys.stderr, flush=True)

    # Precompute landmarks for max k
    max_k = max(K_VALUES)
    print(f"  {name}: {max_k} landmarks...", end="", file=sys.stderr, flush=True)
    t0 = time.perf_counter()
    all_landmarks = select_landmarks(w, h, passable_mask, neighbors, max_k, core_a_i, core_b_i)
    all_tables = build_landmark_table(n, passable_mask, neighbors, all_landmarks)
    lm_ms = (time.perf_counter() - t0) * 1000
    print(f" {lm_ms:.0f}ms", file=sys.stderr, flush=True)

    # Compute reference costs using APSP-guided A* (no timeout, guaranteed optimal)
    print(f"  {name}: reference costs...", end="", file=sys.stderr, flush=True)
    ref_costs: list[int] = []
    for si, gi in pairs:
        if apsp[si][gi] == 0xFF:
            ref_costs.append(_INF)
        else:
            cost, _, _ = astar(
                w, h, tiles, si, gi,
                lambda node, _gi=gi, _a=apsp: h_apsp(node, _gi, _a),
                timeout_ns * 1000,  # generous timeout for reference
            )
            ref_costs.append(cost)
    print(" done", file=sys.stderr, flush=True)

    # Define heuristics
    heuristics: list[tuple[str, object]] = [
        ("manhattan", None),
        ("chebyshev", None),
    ]
    for k in K_VALUES:
        heuristics.append((f"landmark_k{k}", all_tables[:k]))
    heuristics.append(("apsp", apsp))

    results: list[dict] = []

    for hname, hdata in heuristics:
        print(f"  {name}: {hname}...", end="", file=sys.stderr, flush=True)
        times_us: list[float] = []
        expansions: list[int] = []
        tles = 0
        incorrect = 0
        total_tested = 0

        for idx, (si, gi) in enumerate(pairs):
            if apsp[si][gi] == 0xFF:
                continue  # skip unreachable
            total_tested += 1

            if hname == "manhattan":
                hfunc = lambda node, _gi=gi, _w=w: h_manhattan(node, _gi, _w)
            elif hname == "chebyshev":
                hfunc = lambda node, _gi=gi, _w=w: h_chebyshev(node, _gi, _w)
            elif hname == "apsp":
                hfunc = lambda node, _gi=gi, _a=hdata: h_apsp(node, _gi, _a)
            else:
                hfunc = lambda node, _gi=gi, _t=hdata: h_landmark(node, _gi, _t)

            t0 = time.perf_counter()
            cost, exp, tle = astar(w, h, tiles, si, gi, hfunc, timeout_ns)
            elapsed_us = (time.perf_counter() - t0) * 1e6

            times_us.append(elapsed_us)
            expansions.append(exp)
            if tle:
                tles += 1
            elif cost != ref_costs[idx]:
                incorrect += 1

        n_tested = total_tested
        tp = percentiles(times_us)
        ep = percentiles([float(e) for e in expansions])
        mean_time = sum(times_us) / len(times_us) if times_us else 0.0
        mean_exp = sum(expansions) / len(expansions) if expansions else 0.0

        row: dict = {
            "map": name,
            "width": w,
            "height": h,
            "n_tiles": n,
            "n_passable": n_passable,
            "heuristic": hname,
            "pairs_tested": n_tested,
            "tles": tles,
            "incorrect": incorrect,
            "mean_time_us": round(mean_time, 2),
        }
        for key, val in tp:
            row[f"time_{key}_us"] = round(val, 2)
        row["mean_expansions"] = round(mean_exp, 1)
        for key, val in ep:
            row[f"exp_{key}"] = round(val, 1)

        results.append(row)
        print(f" tles={tles} bad={incorrect} mean_exp={mean_exp:.0f}", file=sys.stderr, flush=True)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark landmark heuristics for A*")
    parser.add_argument("--pairs", type=int, default=200, help="Random pairs per map")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-ms", type=float, default=5.0, help="A* timeout in ms")
    parser.add_argument("--output", default=None, help="Output CSV path (default: stdout)")
    args = parser.parse_args()

    print(
        f"Benchmarking {len(list(KnownMap))} maps, {args.pairs} pairs each, "
        f"timeout={args.timeout_ms}ms",
        file=sys.stderr,
    )

    all_results: list[dict] = []
    for km in KnownMap:
        all_results.extend(bench_map(km, args.pairs, args.seed, args.timeout_ms))

    if not all_results:
        print("No results!", file=sys.stderr)
        sys.exit(1)

    fieldnames = list(all_results[0].keys())
    out = open(args.output, "w", newline="") if args.output else sys.stdout  # noqa: SIM115
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_results)
    if args.output:
        out.close()
        print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
