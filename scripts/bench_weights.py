import heapq
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bots" / "intgrah" / "v50"))

from cambc import Environment, Position
from hardcode.known import KnownMap
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode

_INF = 1_000_000
_CR = 2
_CE = 10
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))

WEIGHTS = [1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 50]


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


def dijk(
    cost: list[int], nb: list[list[tuple[int, bool]]], n: int, si: int
) -> list[int]:
    dist = [_INF] * n
    dist[si] = 0
    heap = [(0, si)]
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


def place_roads(
    base_cost: list[int],
    nb: list[list[tuple[int, bool]]],
    n: int,
    w: int,
    ca: Position,
    cb: Position,
    env: list[Environment],
) -> tuple[list[int], int]:
    cost = list(base_cost)
    cai = ca.y * w + ca.x
    ores = [i for i in range(n) if env[i] in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)]
    ore_adj = set()
    for oi in ores:
        for ni, _ in nb[oi]:
            if base_cost[ni] < _INF:
                ore_adj.add(ni)
    targets = list(ore_adj)[:5]
    mx = (ca.x + cb.x) // 2
    my = (ca.y + cb.y) // 2
    mi = my * w + mx
    if base_cost[mi] < _INF:
        targets.append(mi)
    roads = set()
    for target in targets:
        dist = [_INF] * n
        parent = [-1] * n
        dist[cai] = 0
        heap = [(0, cai)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]:
                continue
            if node == target:
                break
            for ni, diag in nb[node]:
                c = base_cost[ni]
                if c >= _INF:
                    continue
                if diag:
                    c += 1
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    parent[ni] = node
                    heapq.heappush(heap, (nd, ni))
        if dist[target] < _INF:
            cur = target
            while cur not in (-1, cai):
                roads.add(cur)
                cur = parent[cur]
    for ri in roads:
        cost[ri] = _CR
    return cost, len(roads)


def astar_w(
    cost: list[int],
    nb: list[list[tuple[int, bool]]],
    n: int,
    w: int,
    si: int,
    gi: int,
    weight: int,
) -> tuple[int, int, float]:
    t0 = time.perf_counter()
    if si == gi:
        return 0, 0, (time.perf_counter() - t0) * 1e6
    gx, gy = gi % w, gi // w
    g = [_INF] * n
    g[si] = 0
    touched = [si]
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * _CR
    heap = [(h_si * weight, si)]
    exp = 0
    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            rc = g[gi]
            for ti in touched:
                g[ti] = _INF
            return rc, exp, (time.perf_counter() - t0) * 1e6
        h_node = max(abs(node % w - gx), abs(node // w - gy)) * _CR
        if f > g[node] + h_node * weight:
            continue
        exp += 1
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
                h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * _CR
                heapq.heappush(heap, (nd + h_ni * weight, ni))
    for ti in touched:
        g[ti] = _INF
    return _INF, exp, (time.perf_counter() - t0) * 1e6


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    vals_s = sorted(vals)
    i = int(len(vals_s) * p / 100)
    i = min(i, len(vals_s) - 1)
    return vals_s[i]


def main() -> None:
    all_opts: dict[str, dict[int, list[float]]] = {}
    all_exps: dict[str, dict[int, list[int]]] = {}
    all_times: dict[str, dict[int, list[float]]] = {}

    for km in KnownMap:
        mw, mh = DIMENSIONS[km]
        n = mw * mh
        env_data = decode(TILES[km](), n)
        impass = (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)
        base_cost = [_INF if env_data[i] in impass else _CE for i in range(n)]
        nb = build_nb(mw, mh)
        passable = [i for i in range(n) if base_cost[i] < _INF]
        ca, cb = CORE_A[km], CORE_B[km]
        rng = random.Random(42)
        pairs = [(rng.choice(passable), rng.choice(passable)) for _ in range(200)]

        for scenario in ["no_roads", "with_roads"]:
            if scenario == "no_roads":
                cost = list(base_cost)
            else:
                cost, _ = place_roads(base_cost, nb, n, mw, ca, cb, env_data)

            gt_cache: dict[int, list[int]] = {}
            for si, gi in pairs:
                if si not in gt_cache:
                    gt_cache[si] = dijk(cost, nb, n, si)

            key = f"{km.value}/{scenario}"
            all_opts[key] = {wt: [] for wt in WEIGHTS}
            all_exps[key] = {wt: [] for wt in WEIGHTS}
            all_times[key] = {wt: [] for wt in WEIGHTS}

            for wt in WEIGHTS:
                for si, gi in pairs:
                    gd = gt_cache[si][gi]
                    if gd >= _INF or gd == 0:
                        continue
                    pc, exp, us = astar_w(cost, nb, n, mw, si, gi, wt)
                    if pc < _INF:
                        all_opts[key][wt].append(pc / gd)
                    else:
                        all_opts[key][wt].append(float("inf"))
                    all_exps[key][wt].append(exp)
                    all_times[key][wt].append(us)

        print(f"  {km.value}", file=sys.stderr, flush=True)

    for scenario in ["no_roads", "with_roads"]:
        print(f"\n{'=' * 200}")
        print(f"  {scenario.upper()}")
        print(f"{'=' * 200}")

        global_opts: dict[int, list[float]] = {wt: [] for wt in WEIGHTS}
        global_exps: dict[int, list[int]] = {wt: [] for wt in WEIGHTS}
        global_times: dict[int, list[float]] = {wt: [] for wt in WEIGHTS}

        for km in KnownMap:
            key = f"{km.value}/{scenario}"
            if key not in all_opts:
                continue
            for wt in WEIGHTS:
                global_opts[wt].extend(all_opts[key][wt])
                global_exps[wt].extend(all_exps[key][wt])
                global_times[wt].extend(all_times[key][wt])

        print(f"\n  OPTIMALITY (path_cost / optimal_cost)")
        hdr = f"  {'w':>4}"
        for label in ["p50", "p75", "p95", "p100"]:
            hdr += f"  {label:>8}"
        print(hdr)
        print(f"  {'-' * 40}")
        for wt in WEIGHTS:
            vals = global_opts[wt]
            line = f"  {wt:>4}"
            for p in [50, 75, 95, 100]:
                v = pct(vals, p)
                line += f"  {v:>8.4f}"
            print(line)

        print(f"\n  EXPANSIONS")
        hdr = f"  {'w':>4}"
        for label in ["p50", "p75", "p95", "p100"]:
            hdr += f"  {label:>8}"
        print(hdr)
        print(f"  {'-' * 40}")
        for wt in WEIGHTS:
            vals = [float(e) for e in global_exps[wt]]
            line = f"  {wt:>4}"
            for p in [50, 75, 95, 100]:
                v = pct(vals, p)
                line += f"  {v:>8.0f}"
            print(line)

        print(f"\n  TIME (us)")
        hdr = f"  {'w':>4}"
        for label in ["p50", "p75", "p95", "p100"]:
            hdr += f"  {label:>8}"
        print(hdr)
        print(f"  {'-' * 40}")
        for wt in WEIGHTS:
            vals = global_times[wt]
            line = f"  {wt:>4}"
            for p in [50, 75, 95, 100]:
                v = pct(vals, p)
                line += f"  {v:>8.0f}"
            print(line)


if __name__ == "__main__":
    main()
