import csv
import heapq
import random
import sys
from collections.abc import Generator
from pathlib import Path

from cambc import Environment, Position
from hardcode.known import KnownMap
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode

_INF = 1_000_000
_CR = 2
_CE = 10
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
    tt: list[int],
    ca: Position,
    cb: Position,
) -> tuple[list[int], int]:
    cost = list(base_cost)
    cai = ca.y * w + ca.x
    ores = [i for i in range(n) if tt[i] in (2, 3)]
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
) -> tuple[int, int]:
    if si == gi:
        return 0, 0
    gx, gy = gi % w, gi // w
    ht = [0] * n
    for i in range(n):
        dx = abs(i % w - gx)
        dy = abs(i // w - gy)
        ht[i] = (max(dy, dx)) * _CR
    g = [_INF] * n
    p = [-1] * n
    g[si] = 0
    touched = [si]
    heap = [(ht[si] * weight, si)]
    exp = 0
    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            rc = g[gi]
            for ti in touched:
                g[ti] = _INF
                p[ti] = -1
            return rc, exp
        if f > g[node] + ht[node] * weight:
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
                p[ni] = node
                heapq.heappush(heap, (nd + ht[ni] * weight, ni))
    for ti in touched:
        g[ti] = _INF
        p[ti] = -1
    return _INF, exp


def main() -> Generator[dict]:
    for km in KnownMap:
        w, h = DIMENSIONS[km]
        n = w * h
        env = decode(TILES[km](), n)
        impass = (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)
        base_cost = [_INF if env[i] in impass else _CE for i in range(n)]
        tt = [1 if env[i] in impass else 0 for i in range(n)]
        nb = build_nb(w, h)
        passable = [i for i in range(n) if base_cost[i] < _INF]
        wall_pct = 100 * (1 - len(passable) / n)
        total_deg = 0
        for i in passable:
            total_deg += sum(1 for ni, _ in nb[i] if base_cost[ni] < _INF)
        avg_deg = total_deg / len(passable)
        ca, cb = CORE_A[km], CORE_B[km]
        rng = random.Random(42)
        pairs = [(rng.choice(passable), rng.choice(passable)) for _ in range(200)]

        for scenario in ["no_roads", "with_roads"]:
            if scenario == "no_roads":
                cost = list(base_cost)
                nr = 0
            else:
                cost, nr = place_roads(base_cost, nb, n, w, tt, ca, cb)
            road_frac = nr / len(passable)
            gt_cache = {}
            torts = []
            for si, gi in pairs:
                if si not in gt_cache:
                    gt_cache[si] = dijk(cost, nb, n, si)
                gd = gt_cache[si][gi]
                if gd >= _INF or gd == 0:
                    continue
                sx, sy = si % w, si // w
                gx, gy = gi % w, gi // w
                cheb = max(abs(sx - gx), abs(sy - gy))
                if cheb == 0:
                    continue
                min_cost = _CR if nr > 0 else _CE
                torts.append(gd / (cheb * min_cost))
            torts.sort()
            nt = len(torts)
            if nt == 0:
                continue
            w_data = {}
            for wt in [1, 2, 3, 4, 5]:
                exps = []
                opts = []
                for si, gi in pairs:
                    gd = gt_cache[si][gi]
                    if gd >= _INF or gd == 0:
                        continue
                    pc, exp = astar_w(cost, nb, n, w, si, gi, wt)
                    exps.append(exp)
                    if wt > 1 and pc < _INF:
                        opts.append(pc / gd)
                w_data[wt] = (
                    sum(exps) / len(exps) if exps else 0,
                    max(opts) if opts else 1.0,
                )
            yield {
                "map": km.value,
                "scenario": scenario,
                "n": n,
                "passable": len(passable),
                "wall_pct": round(wall_pct, 1),
                "avg_degree": round(avg_deg, 2),
                "n_roads": nr,
                "road_frac": round(road_frac, 3),
                "tort_p50": round(torts[nt // 2], 3),
                "tort_p95": round(torts[int(nt * 0.95)], 3),
                "tort_max": round(torts[-1], 3),
                "w1_exp": round(w_data[1][0]),
                "w3_exp": round(w_data[3][0]),
                "w5_exp": round(w_data[5][0]),
                "w2_opt": round(w_data[2][1], 4),
                "w3_opt": round(w_data[3][1], 4),
                "w4_opt": round(w_data[4][1], 4),
                "w5_opt": round(w_data[5][1], 4),
            }
        print(f"  {km.value}", file=sys.stderr, flush=True)


rows = list(main())
# CSV
out = Path(__file__).resolve().parent / "bench_tortuosity.csv"
with out.open("w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    wr.writeheader()
    wr.writerows(rows)

# Summary
for scenario in ["no_roads", "with_roads"]:
    sr = [r for r in rows if r["scenario"] == scenario]
    print(f"\n{'=' * 130}\n  {scenario.upper()}\n{'=' * 130}")
    print(
        f"{'Map':<22} {'N':>5} {'Wall%':>6} {'Deg':>5} {'Roads':>5} {'RdFr':>6} | {'T50':>5} {'T95':>5} {'Tmax':>6} | {'w1exp':>6} {'w3exp':>6} {'w5exp':>6} | {'w2opt':>6} {'w3opt':>6} {'w4opt':>6} {'w5opt':>6}"
    )
    print("-" * 130)
    for r in sr:
        print(
            f"{r['map']:<22} {r['n']:>5} {r['wall_pct']:>5.1f}% {r['avg_degree']:>5.2f} {r['n_roads']:>5} {r['road_frac']:>6.3f}"
            f" | {r['tort_p50']:>5.2f} {r['tort_p95']:>5.2f} {r['tort_max']:>6.2f}"
            f" | {r['w1_exp']:>6} {r['w3_exp']:>6} {r['w5_exp']:>6}"
            f" | {r['w2_opt']:>6.3f} {r['w3_opt']:>6.3f} {r['w4_opt']:>6.3f} {r['w5_opt']:>6.3f}"
        )
    # Safety summary
    print()
    for wt in [2, 3, 4, 5]:
        col = f"w{wt}_opt"
        safe = sum(1 for r in sr if r[col] < 1.05)
        worst = max(r[col] for r in sr)
        avg = sum(r[col] for r in sr) / len(sr)
        print(f"  w={wt}: {safe}/38 safe (<1.05x), worst={worst:.4f}, avg={avg:.4f}")

# Correlation analysis
print(f"\n{'=' * 130}\n  CORRELATION: tort_max vs w3_opt (with roads)\n{'=' * 130}")
wr = [r for r in rows if r["scenario"] == "with_roads"]
wr.sort(key=lambda r: r["w3_opt"], reverse=True)
print(
    f"{'Map':<22} {'tort_max':>8} {'road_frac':>9} {'avg_deg':>7} | {'w3_opt':>7} {'w5_opt':>7}"
)
print("-" * 70)
for r in wr[:15]:
    print(
        f"{r['map']:<22} {r['tort_max']:>8.3f} {r['road_frac']:>9.3f} {r['avg_degree']:>7.2f} | {r['w3_opt']:>7.4f} {r['w5_opt']:>7.4f}"
    )

# Can we predict: w3 is safe when tort_max < X?
print("\n  PREDICTION: w3 safe (<1.05x) when tort_max < threshold?")
for thresh in [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]:
    subset = [r for r in wr if r["tort_max"] < thresh]
    if not subset:
        continue
    all_safe = all(r["w3_opt"] < 1.05 for r in subset)
    print(
        f"    tort_max < {thresh}: {len(subset)} maps, all safe={all_safe}, worst w3={max(r['w3_opt'] for r in subset):.4f}"
    )

print("\n  PREDICTION: w3 safe when road_frac < threshold?")
for thresh in [0.01, 0.02, 0.03, 0.05, 0.10]:
    subset = [r for r in wr if r["road_frac"] < thresh]
    if not subset:
        continue
    all_safe = all(r["w3_opt"] < 1.05 for r in subset)
    print(
        f"    road_frac < {thresh}: {len(subset)} maps, all safe={all_safe}, worst w3={max(r['w3_opt'] for r in subset):.4f}"
    )
