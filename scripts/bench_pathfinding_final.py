"""Comprehensive pathfinding benchmark with true cost model.

Costs: ROAD=2, EMPTY=10, UNSEEN=12, IMPASSABLE=inf. Diagonal +1.
Two test modes:
  A) Full knowledge, 200 random pairs per map (all tiles known, cost=EMPTY or INF)
  B) Exploration sim: builder walks core-to-core discovering tiles (unseen=12)

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
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode

_INF = 1_000_000
_COST_ROAD = 2
_COST_EMPTY = 10
_COST_UNSEEN = 12
_MAX_EDGE = 14
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
_r = math.isqrt(20)
_VIS = [
    (dx, dy)
    for dx in range(-_r, _r + 1)
    for dy in range(-_r, _r + 1)
    if dx * dx + dy * dy <= 20
]


def build_nb(w, h):
    n = w * h
    nb = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append((ny * w + nx, dx != 0 and dy != 0))
    return nb


def build_h(n, w, gi):
    gx, gy = gi % w, gi // w
    h = [0] * n
    for i in range(n):
        dx = abs(i % w - gx)
        dy = abs(i // w - gy)
        h[i] = (max(dy, dx)) * _COST_ROAD
    return h


def val_path(cost, w, path, si, gi):
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


def dijk_gt(cost, nb, n, si):
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


def extr(parent, si, gi):
    if parent[gi] == -1 and gi != si:
        return None
    path = []
    cur = gi
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


# --- ALGORITHMS ---


def astar_heap(cost, nb, n, si, gi, ht, g, p):
    if si == gi:
        return [si]
    g[si] = 0
    touched = [si]
    heap = [(ht[si], si)]
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


def dial_ex(cost, nb, n, si, gi, dist, p):
    if si == gi:
        return [si]
    dist[si] = 0
    touched = [si]
    bk = [deque() for _ in range(_MAX_EDGE)]
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


def w_astar(cost, nb, n, si, gi, ht, g, p, w):
    if si == gi:
        return [si]
    g[si] = 0
    touched = [si]
    heap = [(ht[si] * w, si)]
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


def greedy(cost, nb, n, si, gi, ht, p, v):
    if si == gi:
        return [si]
    touched = [si]
    v[si] = 1
    heap = [(ht[si], si)]
    result = None
    while heap:
        _, node = heapq.heappop(heap)
        if node == gi:
            result = extr(p, si, gi)
            break
        for ni, _diag in nb[node]:
            if cost[ni] >= _INF:
                continue
            if not v[ni]:
                v[ni] = 1
                touched.append(ni)
                p[ni] = node
                heapq.heappush(heap, (ht[ni], ni))
    for ti in touched:
        v[ti] = 0
        p[ti] = -1
    return result


def dial_lim_greedy(cost, nb, n, si, gi, ht, dist, p, lim):
    if si == gi:
        return [si]
    dist[si] = 0
    touched = [si]
    bk = [deque() for _ in range(_MAX_EDGE)]
    bk[0].append(si)
    cur = 0
    result = None
    exp = 0
    bh = _INF
    bn = si
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
        exp += 1
        hv = ht[node]
        if hv < bh:
            bh = hv
            bn = node
        if exp >= lim:
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
    if result is None and bh < _INF:
        partial = extr(p, si, bn)
        if partial:
            c2 = bn
            vs = set(partial)
            seg = []
            for _ in range(n):
                b2 = -1
                bh2 = _INF
                for ni, _ in nb[c2]:
                    if cost[ni] < _INF and ni not in vs and ht[ni] < bh2:
                        bh2 = ht[ni]
                        b2 = ni
                if b2 == -1:
                    break
                vs.add(b2)
                seg.append(b2)
                c2 = b2
                if c2 == gi:
                    result = partial + seg
                    break
    for ti in touched:
        dist[ti] = _INF
        p[ti] = -1
    return result


TECHNIQUES = [
    "astar_heap",
    "dial_exact",
    "weighted_3",
    "weighted_5",
    "weighted_8",
    "greedy_bfs",
    "dial500_greedy",
    "dial1000_greedy",
]


def run(tech, cost, nb, n, w, si, gi, ht, g, p, d, v):
    if tech == "astar_heap":
        return astar_heap(cost, nb, n, si, gi, ht, g, p)
    if tech == "dial_exact":
        return dial_ex(cost, nb, n, si, gi, d, p)
    if tech.startswith("weighted_"):
        return w_astar(cost, nb, n, si, gi, ht, g, p, int(tech.split("_")[1]))
    if tech == "greedy_bfs":
        return greedy(cost, nb, n, si, gi, ht, p, v)
    if "greedy" in tech:
        lim = int(tech.split("_")[0].replace("dial", ""))
        return dial_lim_greedy(cost, nb, n, si, gi, ht, d, p, lim)
    return None


def pct(data, p):
    s = sorted(data)
    idx = min(int(p * len(s)), len(s) - 1)
    return s[idx]


def bench_pairwise(km, seed, n_pairs):
    w, h = DIMENSIONS[km]
    n = w * h
    env = decode(TILES[km](), n)
    tt = [int(e) for e in env]
    cost = [_INF if tt[i] in (1, 2, 3) else _COST_EMPTY for i in range(n)]
    nb = build_nb(w, h)
    ps = [i for i in range(n) if cost[i] < _INF]
    rng = random.Random(seed)
    pairs = [(rng.choice(ps), rng.choice(ps)) for _ in range(n_pairs)]
    gc = {}
    g = [_INF] * n
    p = [-1] * n
    d = [_INF] * n
    v = [0] * n
    results = []
    for tech in TECHNIQUES:
        times = []
        opts = []
        nop = 0
        inv = 0
        for si, gi in pairs:
            if si not in gc:
                gc[si] = dijk_gt(cost, nb, n, si)
            gd = gc[si][gi]
            if gd >= _INF:
                continue
            ht = build_h(n, w, gi)
            t0 = time.perf_counter()
            path = run(tech, cost, nb, n, w, si, gi, ht, g, p, d, v)
            times.append((time.perf_counter() - t0) * 1e6)
            if path and path[-1] == gi:
                pc = val_path(cost, w, path, si, gi)
                if pc > 0:
                    opts.append(pc / gd)
                else:
                    inv += 1
            else:
                nop += 1
        s = sorted(times)
        nt = len(s)
        os = sorted(opts) if opts else [0]
        no = len(os)
        results.append(
            {
                "test": "pairwise",
                "map": km.value,
                "width": w,
                "height": h,
                "n": n,
                "pass": len(ps),
                "tech": tech,
                "pairs": nt,
                "nopath": nop,
                "invalid": inv,
                "t_p50": round(s[nt // 2], 1),
                "t_p95": round(s[int(nt * 0.95)], 1),
                "t_p99": round(pct(times, 0.99), 1),
                "t_max": round(s[-1], 1),
                "t_mean": round(sum(s) / nt, 1),
                "o_p50": round(os[no // 2], 4) if os[0] > 0 else 0,
                "o_p95": round(pct(opts, 0.95), 4) if opts else 0,
                "o_max": round(os[-1], 4) if os[0] > 0 else 0,
                "o_mean": round(sum(opts) / len(opts), 4) if opts else 0,
            }
        )
    return results


def bench_explore(km):
    w, h = DIMENSIONS[km]
    n = w * h
    env = decode(TILES[km](), n)
    tt = [int(e) for e in env]
    ca, cb = CORE_A[km], CORE_B[km]
    gi = cb.y * w + cb.x
    nb = build_nb(w, h)
    g = [_INF] * n
    p = [-1] * n
    d = [_INF] * n
    v = [0] * n
    results = []
    for tech in TECHNIQUES:
        bc = [_COST_UNSEEN] * n
        bx, by = ca.x, ca.y
        times = []
        opts = []
        errs = 0
        nop = 0
        for _turn in range(500):
            for dx, dy in _VIS:
                x, y = bx + dx, by + dy
                if 0 <= x < w and 0 <= y < h:
                    i = y * w + x
                    if bc[i] == _COST_UNSEEN:
                        bc[i] = _INF if tt[i] in (1, 2, 3) else _COST_EMPTY
            si = by * w + bx
            ht = build_h(n, w, gi)
            gt = dijk_gt(bc, nb, n, si)
            gd = gt[gi]
            t0 = time.perf_counter()
            path = run(tech, bc, nb, n, w, si, gi, ht, g, p, d, v)
            times.append((time.perf_counter() - t0) * 1e6)
            if path and path[-1] == gi:
                pc = val_path(bc, w, path, si, gi)
                if pc > 0 and gd > 0 and gd < _INF:
                    opts.append(pc / gd)
                elif pc <= 0:
                    errs += 1
            elif gd < _INF:
                nop += 1
            if path and len(path) >= 2:
                nxt = path[1]
                bx, by = nxt % w, nxt // w
                if bx == cb.x and by == cb.y:
                    break
        s = sorted(times)
        nt = len(s)
        os = sorted(opts) if opts else [0]
        no = len(os)
        ps = sum(1 for t in tt if t == 0)
        results.append(
            {
                "test": "explore",
                "map": km.value,
                "width": w,
                "height": h,
                "n": n,
                "pass": ps,
                "tech": tech,
                "pairs": nt,
                "nopath": nop,
                "invalid": errs,
                "t_p50": round(s[nt // 2], 1),
                "t_p95": round(s[int(nt * 0.95)], 1),
                "t_p99": round(pct(times, 0.99), 1),
                "t_max": round(s[-1], 1),
                "t_mean": round(sum(s) / nt, 1),
                "o_p50": round(os[no // 2], 4) if os[0] > 0 else 0,
                "o_p95": round(pct(opts, 0.95), 4) if opts else 0,
                "o_max": round(os[-1], 4) if os[0] > 0 else 0,
                "o_mean": round(sum(opts) / len(opts), 4) if opts else 0,
            }
        )
    return results


def summary(label, data) -> None:
    print(f"\n{'=' * 130}\n  {label}\n{'=' * 130}")
    print(
        f"{'Tech':<18} {'p50':>6} {'p95':>6} {'max':>6} {'mean':>6} | {'>=2ms':>5} {'>=1ms':>5} {'>=500':>5} | {'o_mean':>7} {'o_p95':>6} {'o_max':>6} | {'nop':>4}"
    )
    print("-" * 110)
    for tech in TECHNIQUES:
        rows = [r for r in data if r["tech"] == tech]
        if not rows:
            continue
        nm = len(rows)
        mx = sorted(r["t_max"] for r in rows)
        p50s = sorted(r["t_p50"] for r in rows)
        means = sorted(r["t_mean"] for r in rows)
        o2 = sum(1 for m in mx if m > 2000)
        o1 = sum(1 for m in mx if m > 1000)
        o5 = sum(1 for m in mx if m > 500)
        nop = sum(r["nopath"] for r in rows)
        om = [r["o_max"] for r in rows if r["o_max"] > 0]
        omn = [r["o_mean"] for r in rows if r["o_mean"] > 0]
        op = [r["o_p95"] for r in rows if r["o_p95"] > 0]
        print(
            f"{tech:<18} {p50s[nm // 2]:>5.0f}u {sorted(r['t_p95'] for r in rows)[nm // 2]:>5.0f}u "
            f"{max(mx):>5.0f}u {means[nm // 2]:>5.0f}u | {o2:>3}/38 {o1:>3}/38 {o5:>3}/38 "
            f"| {sum(omn) / len(omn) if omn else 0:>7.4f} {sorted(op)[len(op) // 2] if op else 0:>6.4f} "
            f"{max(om) if om else 0:>6.4f} | {nop:>4}"
        )


def main() -> None:
    pw = []
    ex = []
    for km in KnownMap:
        print(f"  {km.value}...", file=sys.stderr, flush=True)
        pw.extend(bench_pairwise(km, 42, 200))
        ex.extend(bench_explore(km))
    out = Path(__file__).resolve().parent / "bench_pathfinding_final.csv"
    all_r = pw + ex
    fns = list(all_r[0].keys())
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fns)
        w.writeheader()
        w.writerows(all_r)
    print(f"Wrote {out}", file=sys.stderr)
    summary("PAIRWISE (full knowledge, 200 random pairs/map, EMPTY=10)", pw)
    summary("EXPLORATION (core-to-core, UNSEEN=12, discovering tiles)", ex)


if __name__ == "__main__":
    main()
