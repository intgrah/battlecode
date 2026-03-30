"""Comprehensive pathfinding benchmark: exact + approximate algorithms.

Full-knowledge pairwise tests, 200 random pairs per map, all 38 maps.
Outputs CSV suitable for spreadsheet import.

Usage:
    python -m scripts.bench_pathfinding_final
"""

import csv
import heapq
import math
import random
import sys
import time
import types
from collections import deque
from pathlib import Path

# ---------------------------------------------------------------------------
# Stubs
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


_cambc.Environment = _Env
_cambc.Position = _Pos
sys.modules["cambc"] = _cambc

_util = types.ModuleType("util")
_util.Symmetry = type(
    "S", (), {
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INF = 1_000_000
_COST_ROAD = 2
_COST_EMPTY = 10
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------


def build_neighbors(w: int, h: int) -> list[list[tuple[int, bool]]]:
    n = w * h
    nb: list[list[tuple[int, bool]]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append((ny * w + nx, dx != 0 and dy != 0))
    return nb


def build_h_table(n: int, w: int, gi: int) -> list[int]:
    gx, gy = gi % w, gi // w
    h = [0] * n
    for i in range(n):
        dx = abs(i % w - gx)
        dy = abs(i // w - gy)
        h[i] = (dx if dx > dy else dy) * _COST_ROAD
    return h


def validate_path(cost: list[int], w: int, path: list[int], si: int, gi: int) -> int:
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


def dijkstra_gt(cost: list[int], nb: list[list[tuple[int, bool]]], n: int, si: int) -> list[int]:
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


def extract_path(parent: list[int], si: int, gi: int) -> list[int] | None:
    if parent[gi] == -1 and gi != si:
        return None
    path: list[int] = []
    cur = gi
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


# ---------------------------------------------------------------------------
# EXACT ALGORITHMS
# ---------------------------------------------------------------------------


# 1. A* heap, precomputed h table
def astar_heap(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int, h_table: list[int],
    g: list[int], parent: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    g[si] = 0
    touched = [si]
    heap: list[tuple[int, int]] = [(h_table[si], si)]
    result = None
    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            result = extract_path(parent, si, gi)
            break
        if f > g[node] + h_table[node]:
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
                parent[ni] = node
                heapq.heappush(heap, (nd + h_table[ni], ni))
    for ti in touched:
        g[ti] = _INF
        parent[ti] = -1
    return result


# 2. Dial's algorithm (exact, bucket queue, no heuristic)
def dial_exact(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int,
    dist: list[int], parent: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    MAX_C = 12
    dist[si] = 0
    touched = [si]
    buckets: list[deque[int]] = [deque() for _ in range(MAX_C)]
    buckets[0].append(si)
    current = 0
    result = None
    empty = 0
    while empty < MAX_C:
        bi = current % MAX_C
        if not buckets[bi]:
            current += 1
            empty += 1
            continue
        empty = 0
        node = buckets[bi].popleft()
        if dist[node] != current:
            continue
        if node == gi:
            result = extract_path(parent, si, gi)
            break
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = current + c
            if nd < dist[ni]:
                if dist[ni] == _INF:
                    touched.append(ni)
                dist[ni] = nd
                parent[ni] = node
                buckets[nd % MAX_C].append(ni)
    for ti in touched:
        dist[ti] = _INF
        parent[ti] = -1
    return result


# 3. Dial's with early termination from goal side
def dial_backward(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int,
    dist: list[int], parent: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    MAX_C = 12
    dist[gi] = 0
    touched = [gi]
    buckets: list[deque[int]] = [deque() for _ in range(MAX_C)]
    buckets[0].append(gi)
    current = 0
    empty = 0
    while empty < MAX_C:
        bi = current % MAX_C
        if not buckets[bi]:
            current += 1
            empty += 1
            continue
        empty = 0
        node = buckets[bi].popleft()
        if dist[node] != current:
            continue
        if node == si:
            break
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = current + c
            if nd < dist[ni]:
                if dist[ni] == _INF:
                    touched.append(ni)
                dist[ni] = nd
                parent[ni] = node
                buckets[nd % MAX_C].append(ni)
    result = None
    if dist[si] < _INF:
        # Follow gradient from si to gi.
        path = [si]
        visited = {si}
        cur = si
        while cur != gi:
            best = -1
            best_c = _INF
            for ni, diag in nb[cur]:
                c = cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                t = c + dist[ni]
                if t < best_c and ni not in visited:
                    best_c = t
                    best = ni
            if best == -1:
                break
            visited.add(best)
            path.append(best)
            cur = best
        if cur == gi:
            result = path
    for ti in touched:
        dist[ti] = _INF
        parent[ti] = -1
    return result


# 4. 0-1 BFS on quantised costs
# Quantise: COST_ROAD (2,3) -> 0, COST_EMPTY (10,11) -> 1
# Then run 0-1 BFS. Path cost = count of EMPTY edges * COST_EMPTY + diag adjustments.
# This is a BFS approximation — admissible but not exact for mixed road/empty.
# Actually this doesn't preserve optimality with mixed costs. Skip.


# ---------------------------------------------------------------------------
# APPROXIMATE ALGORITHMS
# ---------------------------------------------------------------------------


# 5. Weighted A* (various weights)
def weighted_astar(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int, h_table: list[int],
    g: list[int], parent: list[int], weight: int,
) -> list[int] | None:
    if si == gi:
        return [si]
    g[si] = 0
    touched = [si]
    heap: list[tuple[int, int]] = [(h_table[si] * weight, si)]
    result = None
    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            result = extract_path(parent, si, gi)
            break
        if f > g[node] + h_table[node] * weight:
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
                parent[ni] = node
                heapq.heappush(heap, (nd + h_table[ni] * weight, ni))
    for ti in touched:
        g[ti] = _INF
        parent[ti] = -1
    return result


# 6. Greedy best-first
def greedy_bfs(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int, h_table: list[int],
    parent: list[int], visited: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    touched = [si]
    visited[si] = 1
    heap: list[tuple[int, int]] = [(h_table[si], si)]
    result = None
    while heap:
        _, node = heapq.heappop(heap)
        if node == gi:
            result = extract_path(parent, si, gi)
            break
        for ni, diag in nb[node]:
            if cost[ni] >= _INF:
                continue
            if not visited[ni]:
                visited[ni] = 1
                touched.append(ni)
                parent[ni] = node
                heapq.heappush(heap, (h_table[ni], ni))
    for ti in touched:
        visited[ti] = 0
        parent[ti] = -1
    return result


# 7. Greedy walk (no heap, just pick best neighbor each step)
def greedy_walk(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int, h_table: list[int],
) -> list[int] | None:
    if si == gi:
        return [si]
    path = [si]
    visited = {si}
    cur = si
    for _ in range(n):
        best = -1
        best_h = _INF
        for ni, diag in nb[cur]:
            if cost[ni] >= _INF:
                continue
            if ni not in visited and h_table[ni] < best_h:
                best_h = h_table[ni]
                best = ni
        if best == -1:
            return None
        visited.add(best)
        path.append(best)
        cur = best
        if cur == gi:
            return path
    return None


# 8. Dial's with expansion limit + greedy fallback
def dial_limited_greedy(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, w: int,
    si: int, gi: int, h_table: list[int],
    dist: list[int], parent: list[int], limit: int,
) -> list[int] | None:
    if si == gi:
        return [si]
    MAX_C = 12
    dist[si] = 0
    touched = [si]
    buckets: list[deque[int]] = [deque() for _ in range(MAX_C)]
    buckets[0].append(si)
    current = 0
    result = None
    expansions = 0
    empty = 0
    best_h = _INF
    best_node = si
    while empty < MAX_C:
        bi = current % MAX_C
        if not buckets[bi]:
            current += 1
            empty += 1
            continue
        empty = 0
        node = buckets[bi].popleft()
        if dist[node] != current:
            continue
        if node == gi:
            result = extract_path(parent, si, gi)
            break
        expansions += 1
        hv = h_table[node]
        if hv < best_h:
            best_h = hv
            best_node = node
        if expansions >= limit:
            break
        for ni, diag in nb[node]:
            c = cost[ni]
            if c >= _INF:
                continue
            if diag:
                c += 1
            nd = current + c
            if nd < dist[ni]:
                if dist[ni] == _INF:
                    touched.append(ni)
                dist[ni] = nd
                parent[ni] = node
                buckets[nd % MAX_C].append(ni)
    if result is None and best_node != si:
        # Greedy walk from best_node to goal.
        partial = extract_path(parent, si, best_node)
        if partial:
            greedy_part = greedy_walk(cost, nb, n, w, best_node, gi, h_table)
            if greedy_part and greedy_part[-1] == gi:
                result = partial + greedy_part[1:]
    for ti in touched:
        dist[ti] = _INF
        parent[ti] = -1
    return result


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

TECHNIQUES = [
    "astar_heap",
    "dial_exact",
    "dial_backward",
    "weighted_3",
    "weighted_5",
    "weighted_8",
    "greedy_bfs",
    "greedy_walk",
    "dial500_greedy",
    "dial1000_greedy",
]


def bench_map(km: KnownMap, seed: int, n_pairs: int) -> list[dict]:
    w, h = DIMENSIONS[km]
    n = w * h
    name = km.value

    env = decode(TILES[km](), n)
    true_tiles = [int(e) for e in env]
    cost = [_INF if true_tiles[i] == 1 else _COST_EMPTY for i in range(n)]
    nb = build_neighbors(w, h)
    passable = [i for i in range(n) if cost[i] < _INF]

    rng = random.Random(seed)
    pairs = [(rng.choice(passable), rng.choice(passable)) for _ in range(n_pairs)]

    # Ground truth cache.
    gt_cache: dict[int, list[int]] = {}

    # Shared arrays.
    g_arr = [_INF] * n
    p_arr = [-1] * n
    d_arr = [_INF] * n
    v_arr = [0] * n

    results: list[dict] = []

    for tech in TECHNIQUES:
        times: list[float] = []
        opt_ratios: list[float] = []
        nopath = 0
        invalid = 0

        for si, gi in pairs:
            if si not in gt_cache:
                gt_cache[si] = dijkstra_gt(cost, nb, n, si)
            gt_dist = gt_cache[si][gi]
            if gt_dist >= _INF:
                continue

            h_table = build_h_table(n, w, gi)

            t0 = time.perf_counter()

            if tech == "astar_heap":
                path = astar_heap(cost, nb, n, w, si, gi, h_table, g_arr, p_arr)
            elif tech == "dial_exact":
                path = dial_exact(cost, nb, n, w, si, gi, d_arr, p_arr)
            elif tech == "dial_backward":
                path = dial_backward(cost, nb, n, w, si, gi, d_arr, p_arr)
            elif tech.startswith("weighted_"):
                wt = int(tech.split("_")[1])
                path = weighted_astar(cost, nb, n, w, si, gi, h_table, g_arr, p_arr, wt)
            elif tech == "greedy_bfs":
                path = greedy_bfs(cost, nb, n, w, si, gi, h_table, p_arr, v_arr)
            elif tech == "greedy_walk":
                path = greedy_walk(cost, nb, n, w, si, gi, h_table)
            elif tech == "dial500_greedy":
                path = dial_limited_greedy(cost, nb, n, w, si, gi, h_table, d_arr, p_arr, 500)
            elif tech == "dial1000_greedy":
                path = dial_limited_greedy(cost, nb, n, w, si, gi, h_table, d_arr, p_arr, 1000)
            else:
                path = None

            elapsed = (time.perf_counter() - t0) * 1e6
            times.append(elapsed)

            if path is not None and path[-1] == gi:
                pc = validate_path(cost, w, path, si, gi)
                if pc > 0:
                    opt_ratios.append(pc / gt_dist)
                else:
                    invalid += 1
            else:
                nopath += 1

        s = sorted(times)
        nt = len(s)
        opt_s = sorted(opt_ratios) if opt_ratios else [0]

        results.append({
            "map": name,
            "width": w,
            "height": h,
            "n_tiles": n,
            "n_passable": len(passable),
            "technique": tech,
            "pairs_tested": nt,
            "nopath": nopath,
            "invalid": invalid,
            "time_p50_us": round(s[nt // 2], 1),
            "time_p95_us": round(s[int(nt * 0.95)], 1),
            "time_p99_us": round(s[min(int(nt * 0.99), nt - 1)], 1),
            "time_max_us": round(s[-1], 1),
            "time_mean_us": round(sum(s) / nt, 1),
            "opt_p50": round(opt_s[len(opt_s) // 2], 4) if opt_s[0] > 0 else 0,
            "opt_p95": round(opt_s[int(len(opt_s) * 0.95)], 4) if opt_s[0] > 0 else 0,
            "opt_max": round(opt_s[-1], 4) if opt_s[0] > 0 else 0,
            "opt_mean": round(sum(opt_ratios) / len(opt_ratios), 4) if opt_ratios else 0,
        })

    return results


def main() -> None:
    all_results: list[dict] = []
    for km in KnownMap:
        print(f"  {km.value}...", file=sys.stderr, flush=True)
        all_results.extend(bench_map(km, seed=42, n_pairs=200))

    # Write CSV.
    out_path = Path(__file__).resolve().parent / "bench_pathfinding_final.csv"
    fieldnames = list(all_results[0].keys())
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
    print(f"Wrote {out_path}", file=sys.stderr)

    # Print aggregate summary to stdout.
    print(
        f"{'Technique':<18} "
        f"{'p50':>7} {'p95':>7} {'max':>7} {'mean':>7} "
        f"| {'>=2ms':>6} {'>=1ms':>6} {'>=500u':>7} "
        f"| {'opt_p50':>8} {'opt_p95':>8} {'opt_max':>8} {'opt_mean':>9} "
        f"| {'nopath':>6} {'inv':>4}"
    )
    print("=" * 130)
    for tech in TECHNIQUES:
        rows = [r for r in all_results if r["technique"] == tech]
        # Aggregate: median of per-map medians, max of per-map maxes, etc.
        maxes = sorted(r["time_max_us"] for r in rows)
        p50s = sorted(r["time_p50_us"] for r in rows)
        means = sorted(r["time_mean_us"] for r in rows)
        nm = len(rows)
        over_2ms = sum(1 for m in maxes if m > 2000)
        over_1ms = sum(1 for m in maxes if m > 1000)
        over_500 = sum(1 for m in maxes if m > 500)
        total_nopath = sum(r["nopath"] for r in rows)
        total_inv = sum(r["invalid"] for r in rows)
        opt_maxes = [r["opt_max"] for r in rows if r["opt_max"] > 0]
        opt_means = [r["opt_mean"] for r in rows if r["opt_mean"] > 0]
        opt_p50s = [r["opt_p50"] for r in rows if r["opt_p50"] > 0]
        opt_p95s = [r["opt_p95"] for r in rows if r["opt_p95"] > 0]
        print(
            f"{tech:<18} "
            f"{p50s[nm//2]:>6.0f}u {sorted(r['time_p95_us'] for r in rows)[nm//2]:>6.0f}u "
            f"{max(maxes):>6.0f}u {means[nm//2]:>6.0f}u "
            f"| {over_2ms:>4}/38 {over_1ms:>4}/38 {over_500:>5}/38 "
            f"| {sorted(opt_p50s)[len(opt_p50s)//2]:>8.4f} {sorted(opt_p95s)[len(opt_p95s)//2]:>8.4f} "
            f"{max(opt_maxes):>8.4f} {sum(opt_means)/len(opt_means):>9.4f} "
            f"| {total_nopath:>6} {total_inv:>4}"
        )


if __name__ == "__main__":
    main()
