import argparse
import heapq
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "bots" / "intgrah" / "v50")
)

from algorithms.hpastar import GatewayGraph

from proto.cambc_pb2 import Map as PbMap

_INF = 1_000_000
_COST_EMPTY = 10
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def load_map(path: Path) -> tuple[int, int, list[int]]:
    m = PbMap()
    m.ParseFromString(path.read_bytes())
    tiles: list[int] = []
    for row in m.rows:
        tiles.extend(row.tiles)
    return m.width, m.height, tiles


def tile_cost_fn(
    tiles: list[int],
    w: int,
) -> Callable[[int, int], int]:
    def cost(x: int, y: int) -> int:
        t = tiles[y * w + x]
        if t in {1, 2, 3}:
            return _INF
        return _COST_EMPTY

    return cost


def dijkstra_full(
    w: int,
    h: int,
    tiles: list[int],
    sx: int,
    sy: int,
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
                t = tiles[ni]
                if t in {1, 2, 3}:
                    continue
                c = _COST_EMPTY
                if dx != 0 and dy != 0:
                    c += 1
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    heapq.heappush(heap, (nd, ni))
    return dist


def astar_chebyshev(
    w: int,
    h: int,
    tiles: list[int],
    sx: int,
    sy: int,
    gx: int,
    gy: int,
) -> tuple[int, int]:
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
                t = tiles[ni]
                if t in {1, 2, 3}:
                    continue
                c = _COST_EMPTY
                if dx != 0 and dy != 0:
                    c += 1
                nd = gn + c
                if nd < g.get(ni, _INF):
                    g[ni] = nd
                    h_val = max(abs(nx - gx), abs(ny - gy)) * _COST_EMPTY
                    heapq.heappush(heap, (nd + h_val, h_val, ni))

    return _INF, expanded


def bench_map(
    map_path: Path,
    n_pairs: int,
    rng_seed: int,
) -> dict:
    w, h, tiles = load_map(map_path)
    cost_fn = tile_cost_fn(tiles, w)

    passable = [(x, y) for y in range(h) for x in range(w) if tiles[y * w + x] == 0]

    if len(passable) < 2:
        return {"name": map_path.stem, "skip": True}

    rng = random.Random(rng_seed)
    pairs: list[tuple[int, int, int, int]] = []
    for _ in range(n_pairs):
        a = rng.choice(passable)
        b = rng.choice(passable)
        pairs.append((a[0], a[1], b[0], b[1]))

    t0 = time.perf_counter()
    gg = GatewayGraph(w, h, cost_fn, cluster_size=7)
    precompute_ms = (time.perf_counter() - t0) * 1000

    n_gw = len(gg._gw_tile)  # noqa: SLF001

    baseline_times: list[float] = []
    baseline_expanded: list[int] = []
    baseline_costs: list[int] = []
    hpa_times: list[float] = []
    hpa_costs: list[int] = []
    optimality_ratios: list[float] = []
    heuristic_times: list[float] = []
    reachable_correct = 0
    total_tested = 0
    longest_optimal = 0

    for sx, sy, gx, gy in pairs:
        optimal_dist = dijkstra_full(w, h, tiles, sx, sy)
        gi = gy * w + gx
        optimal = optimal_dist[gi]
        if optimal < _INF and optimal > longest_optimal:
            longest_optimal = optimal

        t0 = time.perf_counter()
        bl_cost, bl_exp = astar_chebyshev(w, h, tiles, sx, sy, gx, gy)
        baseline_times.append((time.perf_counter() - t0) * 1e6)
        baseline_expanded.append(bl_exp)
        baseline_costs.append(bl_cost)

        t0 = time.perf_counter()
        path = gg.find_path(sx, sy, gx, gy)
        hpa_times.append((time.perf_counter() - t0) * 1e6)

        if path is not None:
            hpa_cost, err = _validate_path(w, h, tiles, path, sx, sy, gx, gy)
            if err is not None:
                print(f"  INVALID PATH on {map_path.stem} ({sx},{sy})->({gx},{gy}): {err}", file=sys.stderr)
            hpa_costs.append(hpa_cost)
        else:
            hpa_costs.append(_INF)

        t0 = time.perf_counter()
        si = sy * w + sx
        gg.heuristic(si, gi)
        heuristic_times.append((time.perf_counter() - t0) * 1e6)

        total_tested += 1
        is_reachable = optimal < _INF
        found = path is not None
        if is_reachable == found:
            reachable_correct += 1
        elif is_reachable and not found:
            print(f"  FALSE NEG on {map_path.stem} ({sx},{sy})->({gx},{gy})", file=sys.stderr)
        elif not is_reachable and found:
            print(f"  FALSE POS on {map_path.stem} ({sx},{sy})->({gx},{gy})", file=sys.stderr)

        if 0 < optimal < _INF and hpa_costs[-1] < _INF:
            optimality_ratios.append(hpa_costs[-1] / optimal)

    return {
        "name": map_path.stem,
        "size": f"{w}x{h}",
        "passable": len(passable),
        "gateways": n_gw,
        "precompute_ms": round(precompute_ms, 1),
        "pairs": n_pairs,
        "reachable_accuracy": f"{reachable_correct}/{total_tested}",
        "baseline_time_us": round(median(baseline_times), 0) if baseline_times else 0,
        "baseline_expanded": round(mean(baseline_expanded), 0)
        if baseline_expanded
        else 0,
        "hpa_time_us": round(median(hpa_times), 0) if hpa_times else 0,
        "hpa_max_us": round(max(hpa_times), 0) if hpa_times else 0,
        "bl_max_us": round(max(baseline_times), 0) if baseline_times else 0,
        "heuristic_time_us": round(median(heuristic_times), 0)
        if heuristic_times
        else 0,
        "longest_opt": longest_optimal,
        "optimality_mean": round(mean(optimality_ratios), 3)
        if optimality_ratios
        else 0,
        "optimality_worst": round(max(optimality_ratios), 3)
        if optimality_ratios
        else 0,
    }


def _validate_path(
    w: int, h: int, tiles: list[int], path: list[int], sx: int, sy: int, gx: int, gy: int,
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
        t = tiles[path[i + 1]]
        if t in {1, 2, 3}:
            return _INF, f"impassable tile step {i}: ({x1},{y1}) type={t}"
        c = _COST_EMPTY
        if dx != 0 and dy != 0:
            c += 1
        total += c
    return total, None


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", default="maps/", help="Directory with .map26 files")
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    map_dir = Path(args.maps)
    map_files = sorted(map_dir.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {map_dir}")
        sys.exit(1)

    print(
        f"{'Map':<30} {'Size':>6} {'GW':>4} {'Pre ms':>7} "
        f"{'BL us':>7} {'BL max':>7} {'HPA us':>7} {'HPA max':>8} "
        f"{'Opt mean':>9} {'Opt worst':>10} {'LongPath':>8} {'Reach':>8}"
    )
    print("-" * 140)

    for mf in map_files:
        r = bench_map(mf, args.pairs, args.seed)
        if r.get("skip"):
            print(f"{r['name']:<30} SKIPPED")
            continue
        print(
            f"{r['name']:<30} {r['size']:>6} {r['gateways']:>4} {r['precompute_ms']:>7} "
            f"{r['baseline_time_us']:>7.0f} {r['bl_max_us']:>7.0f} {r['hpa_time_us']:>7.0f} {r['hpa_max_us']:>8.0f} "
            f"{r['optimality_mean']:>9.3f} {r['optimality_worst']:>10.3f} {r['longest_opt']:>8} {r['reachable_accuracy']:>8}"
        )


if __name__ == "__main__":
    main()
