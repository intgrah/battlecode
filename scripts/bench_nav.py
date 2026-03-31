"""Unified navigation benchmark.

Runs all pathfinding algorithms across all 38 known maps, 200 random pairs each.
No dependency on bots/ or cambc. Only needs proto/cambc_pb2.py for map loading
and bots/intgrah/v50/algorithms/hpastar.py (imported by path).

Usage:
    python scripts/bench_nav.py
    pypy scripts/bench_nav.py
"""

from __future__ import annotations

import csv
import heapq
import random
import sys
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from proto.cambc_pb2 import Map as PbMap
from scripts.hpastar import GatewayGraph

MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"

INF = 1_000_000
CR = 1
CE = 3
DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))

N_PAIRS = 200
SEED = 42

Path_ = list[int] | None
AlgoFn = Callable[["MapData", int, int], Path_]
AlgoEntry = tuple[str, AlgoFn, bool]


# ---------------------------------------------------------------------------
# Map loading (protobuf, no cambc dependency)
# tile values: 0=empty, 1=wall, 2=ore_titanium, 3=ore_axionite
# ---------------------------------------------------------------------------


def _load_map(path: Path) -> tuple[int, int, list[int]]:
    m = PbMap()
    m.ParseFromString(path.read_bytes())
    tiles: list[int] = []
    for row in m.rows:
        tiles.extend(row.tiles)
    return m.width, m.height, tiles


class MapData:
    __slots__ = (
        "apsp",
        "cost",
        "h",
        "hpa_graph",
        "n",
        "name",
        "nb",
        "offsets_card",
        "offsets_diag",
        "passable",
        "tiles",
        "w",
    )

    def __init__(self, map_path: Path) -> None:
        self.name: str = map_path.stem
        self.w: int
        self.h: int
        self.w, self.h, self.tiles = _load_map(map_path)
        self.n: int = self.w * self.h
        self.cost: list[int] = [
            INF if self.tiles[i] in (1, 2, 3) else CE for i in range(self.n)
        ]
        self.nb: list[list[int]] = _build_nb(self.w, self.h)
        self.passable: list[int] = [i for i in range(self.n) if self.cost[i] < INF]
        self.offsets_card: tuple[int, ...] = (-self.w, -1, 1, self.w)
        w = self.w
        self.offsets_diag: tuple[int, ...] = (-w - 1, -w + 1, w - 1, w + 1)
        self.apsp: ApspTable | None = None
        self.hpa_graph: GatewayGraph | None = None

    def reset_cost_no_roads(self) -> None:
        self.cost = [INF if self.tiles[i] in (1, 2, 3) else CE for i in range(self.n)]
        self.passable = [i for i in range(self.n) if self.cost[i] < INF]
        self.hpa_graph = None

    def place_roads(self) -> int:
        n, nb = self.n, self.nb
        cost = self.cost
        tiles = self.tiles
        ores: list[int] = [i for i in range(n) if tiles[i] in (2, 3)]
        ore_adj: set[int] = set()
        for oi in ores:
            for ni in nb[oi]:
                if cost[ni] < INF:
                    ore_adj.add(ni)
        targets = list(ore_adj)[:5]
        core_i = self.passable[0] if self.passable else 0
        roads: set[int] = set()
        for target in targets:
            dist: list[int] = [INF] * n
            parent: list[int] = [-1] * n
            dist[core_i] = 0
            heap: list[tuple[int, int]] = [(0, core_i)]
            while heap:
                d, node = heapq.heappop(heap)
                if d > dist[node]:
                    continue
                if node == target:
                    break
                for ni in nb[node]:
                    c = cost[ni]
                    if c >= INF:
                        continue
                    nd = d + c
                    if nd < dist[ni]:
                        dist[ni] = nd
                        parent[ni] = node
                        heapq.heappush(heap, (nd, ni))
            if dist[target] < INF:
                cur = target
                while cur not in (-1, core_i):
                    roads.add(cur)
                    cur = parent[cur]
        for ri in roads:
            cost[ri] = CR
        self.passable = [i for i in range(n) if cost[i] < INF]
        self.hpa_graph = None
        return len(roads)


def _build_nb(w: int, h: int) -> list[list[int]]:
    n = w * h
    nb: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append(ny * w + nx)
    return nb


# ---------------------------------------------------------------------------
# Ground truth: full Dijkstra + all optimal first moves
# ---------------------------------------------------------------------------


def dijkstra_full(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.nb
    dist: list[int] = [INF] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni in nb[node]:
            c = cost[ni]
            if c >= INF:
                continue
            nd = d + c
            if nd < dist[ni]:
                dist[ni] = nd
                heapq.heappush(heap, (nd, ni))
    return dist


def optimal_first_moves(md: MapData, si: int, gi: int, dist: list[int]) -> set[int]:
    if si == gi:
        return {si}
    if dist[gi] >= INF:
        return set()
    cost, nb = md.cost, md.nb
    n = md.n
    on_shortest: list[bool] = [False] * n
    on_shortest[gi] = True
    q: deque[int] = deque([gi])
    while q:
        node = q.popleft()
        for ni in nb[node]:
            if on_shortest[ni]:
                continue
            c = cost[node]
            if c >= INF:
                continue
            if dist[ni] + c == dist[node]:
                on_shortest[ni] = True
                q.append(ni)
    moves: set[int] = set()
    for ni in nb[si]:
        if not on_shortest[ni]:
            continue
        c = cost[ni]
        if c >= INF:
            continue
        if dist[si] + c == dist[ni]:
            moves.add(ni)
    return moves


# ---------------------------------------------------------------------------
# Algorithm implementations
# ---------------------------------------------------------------------------


def _extract(parent: list[int], si: int, node: int) -> Path_:
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur = node
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def algo_astar_heap(
    md: MapData,
    si: int,
    gi: int,
    weight: int = 1,
    budget: int = 0,
) -> Path_:
    w, n, cost, nb = md.w, md.n, md.cost, md.nb
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
    g: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    g[si] = 0
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * CR
    heap: list[tuple[int, int, int]] = [(h_si * weight, h_si, si)]
    exp = 0
    best_h = INF
    best_node = si
    while heap:
        f, _, node = heapq.heappop(heap)
        if node == gi:
            return _extract(parent, si, gi)
        h_node = max(abs(node % w - gx), abs(node // w - gy)) * CR
        if f > g[node] + h_node * weight:
            continue
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if budget > 0 and exp >= budget:
            return _extract(parent, si, best_node)
        gn = g[node]
        for ni in nb[node]:
            c = cost[ni]
            if c >= INF:
                continue
            nd = gn + c
            if nd < g[ni]:
                g[ni] = nd
                parent[ni] = node
                h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
                heapq.heappush(heap, (nd + h_ni * weight, h_ni, ni))
    if best_h < INF:
        return _extract(parent, si, best_node)
    return None


def algo_astar_bucket(
    md: MapData,
    si: int,
    gi: int,
    weight: int = 1,
    budget: int = 0,
) -> Path_:
    w, n, cost = md.w, md.n, md.cost
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
    offsets_card = md.offsets_card
    offsets_diag = md.offsets_diag
    mod = CE + weight + 1
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    ht: list[int] = [-1] * n
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * CR
    ht[si] = h_si
    ht[gi] = 0
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[h_si * weight % mod].append(si)
    cur_f = h_si * weight
    emp = 0
    exp = 0
    best_h = INF
    best_node = si
    while emp < mod:
        bi = cur_f % mod
        if not bk[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        h_node = ht[node]
        if dist[node] + h_node * weight != cur_f:
            continue
        if node == gi:
            return _extract(parent, si, gi)
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if budget > 0 and exp >= budget:
            return _extract(parent, si, best_node)
        gn = dist[node]
        cx = node % w
        at_left = cx == 0
        at_right = cx == w - 1
        for off in offsets_card:
            ni = node + off
            if 0 <= ni < n:
                if off == -1 and at_left:
                    continue
                if off == 1 and at_right:
                    continue
                c = cost[ni]
                if c < INF:
                    nd = gn + c
                    if nd < dist[ni]:
                        dist[ni] = nd
                        parent[ni] = node
                        h_ni = ht[ni]
                        if h_ni < 0:
                            h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
                            ht[ni] = h_ni
                        bk[(nd + h_ni * weight) % mod].append(ni)
        for off in offsets_diag:
            ni = node + off
            if 0 <= ni < n:
                if (off == -w - 1 or off == w - 1) and at_left:
                    continue
                if (off == -w + 1 or off == w + 1) and at_right:
                    continue
                c = cost[ni]
                if c < INF:
                    nd = gn + c
                    if nd < dist[ni]:
                        dist[ni] = nd
                        parent[ni] = node
                        h_ni = ht[ni]
                        if h_ni < 0:
                            h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
                            ht[ni] = h_ni
                        bk[(nd + h_ni * weight) % mod].append(ni)
    if best_h < INF:
        return _extract(parent, si, best_node)
    return None


def algo_bfs(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    n, cost, nb = md.n, md.cost, md.nb
    if si == gi:
        return [si]
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    exp = 0
    found = False
    best_node = si
    while q:
        node = q.popleft()
        exp += 1
        if budget > 0 and exp >= budget:
            best_node = node
            break
        for ni in nb[node]:
            if cost[ni] >= INF:
                continue
            if parent[ni] != -1:
                continue
            parent[ni] = node
            if ni == gi:
                found = True
                break
            q.append(ni)
        if found:
            break
    target = gi if found else (best_node if budget > 0 and best_node != si else -1)
    if target < 0:
        return None
    path: list[int] = []
    cur = target
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path


def algo_gbfs(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    w, n, cost, nb = md.w, md.n, md.cost, md.nb
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
    parent: list[int] = [-1] * n
    parent[si] = si
    visited: list[bool] = [False] * n
    visited[si] = True
    h_si = max(abs(si % w - gx), abs(si // w - gy)) * CR
    heap: list[tuple[int, int]] = [(h_si, si)]
    exp = 0
    best_h = INF
    best_node = si
    while heap:
        h_node, node = heapq.heappop(heap)
        if node == gi:
            best_node = gi
            break
        if not visited[node]:
            continue
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if budget > 0 and exp >= budget:
            break
        for ni in nb[node]:
            c = cost[ni]
            if c >= INF:
                continue
            if visited[ni]:
                continue
            visited[ni] = True
            parent[ni] = node
            h_ni = max(abs(ni % w - gx), abs(ni // w - gy)) * CR
            heapq.heappush(heap, (h_ni, ni))
    if best_node == si or parent[best_node] == -1:
        return None
    path: list[int] = []
    cur = best_node
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path


def algo_dijkstra_heap(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    n, cost, nb = md.n, md.cost, md.nb
    if si == gi:
        return [si]
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    exp = 0
    last_node = si
    while heap:
        d, node = heapq.heappop(heap)
        if node == gi:
            return _extract(parent, si, gi)
        if d > dist[node]:
            continue
        last_node = node
        exp += 1
        if budget > 0 and exp >= budget:
            return _extract(parent, si, last_node)
        gn = dist[node]
        for ni in nb[node]:
            c = cost[ni]
            if c >= INF:
                continue
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                heapq.heappush(heap, (nd, ni))
    return _extract(parent, si, last_node)


def algo_dijkstra_bucket(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    w, n, cost = md.w, md.n, md.cost
    if si == gi:
        return [si]
    offsets_card = md.offsets_card
    offsets_diag = md.offsets_diag
    mod = CE + 1
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    exp = 0
    while emp < mod:
        bi = cur_d % mod
        if not bk[bi]:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        if dist[node] != cur_d:
            continue
        if node == gi:
            return _extract(parent, si, gi)
        exp += 1
        if budget > 0 and exp >= budget:
            return _extract(parent, si, node)
        gn = dist[node]
        cx = node % w
        at_left = cx == 0
        at_right = cx == w - 1
        for off in offsets_card:
            ni = node + off
            if 0 <= ni < n:
                if off == -1 and at_left:
                    continue
                if off == 1 and at_right:
                    continue
                c = cost[ni]
                if c < INF:
                    nd = gn + c
                    if nd < dist[ni]:
                        dist[ni] = nd
                        parent[ni] = node
                        bk[nd % mod].append(ni)
        for off in offsets_diag:
            ni = node + off
            if 0 <= ni < n:
                if (off == -w - 1 or off == w - 1) and at_left:
                    continue
                if (off == -w + 1 or off == w + 1) and at_right:
                    continue
                c = cost[ni]
                if c < INF:
                    nd = gn + c
                    if nd < dist[ni]:
                        dist[ni] = nd
                        parent[ni] = node
                        bk[nd % mod].append(ni)
    return None


# ---------------------------------------------------------------------------
# APSP (weighted Dijkstra per passable tile)
# ---------------------------------------------------------------------------


class ApspTable:
    __slots__ = ("_rows",)

    def __init__(self, rows: list[list[int]]) -> None:
        self._rows = rows

    def dist(self, a: int, b: int) -> int:
        return self._rows[a][b]


def precompute_apsp(md: MapData) -> None:
    n, cost, nb = md.n, md.cost, md.nb
    rows: list[list[int]] = []
    for si in range(n):
        if cost[si] >= INF:
            rows.append([INF] * n)
            continue
        dist: list[int] = [INF] * n
        dist[si] = 0
        heap: list[tuple[int, int]] = [(0, si)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist[node]:
                continue
            for ni in nb[node]:
                c = cost[ni]
                if c >= INF:
                    continue
                nd = d + c
                if nd < dist[ni]:
                    dist[ni] = nd
                    heapq.heappush(heap, (nd, ni))
        rows.append(dist)
    md.apsp = ApspTable(rows)


def algo_astar_apsp(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    w, n, cost = md.w, md.n, md.cost
    apsp = md.apsp
    assert apsp is not None
    if si == gi:
        return [si]
    g: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    g[si] = 0
    h0 = apsp.dist(si, gi)
    heap: list[tuple[int, int, int]] = [(h0, h0, si)]
    exp = 0
    best_h = INF
    best_node = si
    while heap:
        f, _, node = heapq.heappop(heap)
        if node == gi:
            return _extract(parent, si, gi)
        hv = apsp.dist(node, gi)
        if f > g[node] + hv:
            continue
        exp += 1
        if hv < best_h:
            best_h = hv
            best_node = node
        if budget > 0 and exp >= budget:
            return _extract(parent, si, best_node)
        gn = g[node]
        cx, cy = node % w, node // w
        for dx, dy in DIR8:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= md.h:
                continue
            ni = ny * w + nx
            c = cost[ni]
            if c >= INF:
                continue
            nd = gn + c
            if nd < g[ni]:
                g[ni] = nd
                parent[ni] = node
                h_ni = apsp.dist(ni, gi)
                heapq.heappush(heap, (nd + h_ni, h_ni, ni))
    if best_h < INF:
        return _extract(parent, si, best_node)
    return None


# ---------------------------------------------------------------------------
# HPA*
# ---------------------------------------------------------------------------


def precompute_hpa(md: MapData) -> None:
    def tile_cost(x: int, y: int) -> int:
        return md.cost[y * md.w + x]

    md.hpa_graph = GatewayGraph(md.w, md.h, tile_cost, cluster_size=7)


def algo_hpa(md: MapData, si: int, gi: int) -> Path_:
    assert md.hpa_graph is not None
    sx, sy = si % md.w, si // md.w
    gx, gy = gi % md.w, gi // md.w
    return md.hpa_graph.find_path(sx, sy, gx, gy)


# ---------------------------------------------------------------------------
# Path cost computation
# ---------------------------------------------------------------------------


def path_cost(md: MapData, path: list[int]) -> int:
    if len(path) < 2:
        return 0
    w, cost = md.w, md.cost
    total = 0
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        ax, ay = a % w, a // w
        bx, by = b % w, b // w
        dx, dy = abs(bx - ax), abs(by - ay)
        if dx > 1 or dy > 1:
            return INF
        c = cost[b]
        if c >= INF:
            return INF
        total += c
    return total


# ---------------------------------------------------------------------------
# Algorithm registry
# ---------------------------------------------------------------------------


def _make_algos() -> list[AlgoEntry]:
    algos: list[AlgoEntry] = []

    for w in [1, 3]:
        for b in [200, 1000, 0]:
            bname = str(b) if b else "inf"
            algos.append(
                (
                    f"a*heap cheb w={w} b={bname}",
                    lambda md, si, gi, _w=w, _b=b: algo_astar_heap(
                        md,
                        si,
                        gi,
                        weight=_w,
                        budget=_b,
                    ),
                    False,
                ),
            )

    for w in [1, 3]:
        for b in [200, 1000, 0]:
            bname = str(b) if b else "inf"
            algos.append(
                (
                    f"a*bucket cheb w={w} b={bname}",
                    lambda md, si, gi, _w=w, _b=b: algo_astar_bucket(
                        md,
                        si,
                        gi,
                        weight=_w,
                        budget=_b,
                    ),
                    False,
                ),
            )

    for b in [200, 1000, 0]:
        bname = str(b) if b else "inf"
        algos.append(
            (
                f"a*heap apsp b={bname}",
                lambda md, si, gi, _b=b: algo_astar_apsp(
                    md,
                    si,
                    gi,
                    budget=_b,
                ),
                True,
            ),
        )

    for b in [200, 1000, 0]:
        bname = str(b) if b else "inf"
        algos.append(
            (
                f"bfs b={bname}",
                lambda md, si, gi, _b=b: algo_bfs(md, si, gi, budget=_b),
                False,
            ),
        )

    for b in [200, 1000, 0]:
        bname = str(b) if b else "inf"
        algos.append(
            (
                f"gbfs b={bname}",
                lambda md, si, gi, _b=b: algo_gbfs(md, si, gi, budget=_b),
                False,
            ),
        )

    for b in [200, 1000, 0]:
        bname = str(b) if b else "inf"
        algos.append(
            (
                f"dijkstra heap b={bname}",
                lambda md, si, gi, _b=b: algo_dijkstra_heap(md, si, gi, budget=_b),
                False,
            ),
        )

    for b in [200, 1000, 0]:
        bname = str(b) if b else "inf"
        algos.append(
            (
                f"dijkstra bucket b={bname}",
                lambda md, si, gi, _b=b: algo_dijkstra_bucket(md, si, gi, budget=_b),
                False,
            ),
        )

    algos.append(
        (
            "hpa* excl precomp",
            algo_hpa,
            True,
        ),
    )

    return algos


ALGOS: list[AlgoEntry] = _make_algos()


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------


def progress_bar(current: int, total: int, width: int = 40, prefix: str = "") -> None:
    frac = current / total if total else 1.0
    filled = int(width * frac)
    bar = "#" * filled + "-" * (width - filled)
    pct = frac * 100
    sys.stderr.write(f"\r{prefix}[{bar}] {pct:5.1f}% ({current}/{total})")
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------


SCENARIOS = ("no_roads", "with_roads")

CSV_FIELDS = [
    "algo",
    "scenario",
    "map",
    "si",
    "gi",
    "time_us",
    "reachable",
    "reached_goal",
    "opt_ratio",
    "first_move_correct",
]


def main() -> None:
    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_maps = len(map_files)
    needs_apsp = any(req for _, _, req in ALGOS if req)
    needs_hpa = any("hpa" in name for name, _, _ in ALGOS)
    n_algos = len(ALGOS)
    n_scenarios = len(SCENARIOS)
    total_work = n_maps * n_scenarios * (n_algos + 1)
    done = 0

    out_path = Path(__file__).resolve().parent / "bench_nav.csv"
    out_f = out_path.open("w", newline="")
    writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDS)
    writer.writeheader()

    hpa_precomp_times: list[float] = []
    hpa_excl_rows: list[dict[str, str | int]] = []

    for mf in map_files:
        md = MapData(mf)
        if not md.passable:
            done += n_scenarios * (n_algos + 1)
            progress_bar(done, total_work, prefix=f"{md.name:24s} ")
            continue

        rng = random.Random(SEED)
        pairs = [
            (rng.choice(md.passable), rng.choice(md.passable)) for _ in range(N_PAIRS)
        ]

        if needs_apsp:
            md.reset_cost_no_roads()
            precompute_apsp(md)

        for scenario in SCENARIOS:
            md.reset_cost_no_roads()
            if scenario == "with_roads":
                md.place_roads()

            prefix = f"{md.name:24s} {scenario:11s} "

            gt_cache: dict[int, list[int]] = {}
            first_moves_cache: dict[tuple[int, int], set[int]] = {}
            for si, gi in pairs:
                if si not in gt_cache:
                    gt_cache[si] = dijkstra_full(md, si)
                key = (si, gi)
                if key not in first_moves_cache:
                    first_moves_cache[key] = optimal_first_moves(
                        md,
                        si,
                        gi,
                        gt_cache[si],
                    )

            done += 1
            progress_bar(done, total_work, prefix=prefix)

            if needs_hpa:
                t0 = time.perf_counter()
                precompute_hpa(md)
                hpa_precomp_times.append((time.perf_counter() - t0) * 1e6)

            for algo_name, algo_fn, req_apsp in ALGOS:
                if req_apsp and md.apsp is None and md.hpa_graph is None:
                    done += 1
                    progress_bar(done, total_work, prefix=prefix)
                    continue

                for si, gi in pairs:
                    gd = gt_cache[si][gi]
                    reachable = gd < INF

                    if not reachable:
                        t0 = time.perf_counter()
                        algo_fn(md, si, gi)
                        us = (time.perf_counter() - t0) * 1e6
                        row: dict[str, str | int] = {
                            "algo": algo_name,
                            "scenario": scenario,
                            "map": md.name,
                            "si": si,
                            "gi": gi,
                            "time_us": f"{us:.1f}",
                            "reachable": 0,
                            "reached_goal": "",
                            "opt_ratio": "",
                            "first_move_correct": "",
                        }
                        writer.writerow(row)
                        if "excl precomp" in algo_name:
                            hpa_excl_rows.append(row)
                        continue

                    if si == gi:
                        row = {
                            "algo": algo_name,
                            "scenario": scenario,
                            "map": md.name,
                            "si": si,
                            "gi": gi,
                            "time_us": "0.0",
                            "reachable": 1,
                            "reached_goal": 1,
                            "opt_ratio": "1.0",
                            "first_move_correct": 1,
                        }
                        writer.writerow(row)
                        if "excl precomp" in algo_name:
                            hpa_excl_rows.append(row)
                        continue

                    t0 = time.perf_counter()
                    path = algo_fn(md, si, gi)
                    us = (time.perf_counter() - t0) * 1e6

                    reached = 0
                    opt = ""
                    fm = 0
                    if path is not None and len(path) >= 1:
                        pc = path_cost(md, path)
                        if path[-1] == gi and pc < INF:
                            reached = 1
                            opt = f"{pc / gd:.6f}"
                        fm_set = first_moves_cache[(si, gi)]
                        if len(path) >= 2 and path[1] in fm_set:
                            fm = 1

                    row = {
                        "algo": algo_name,
                        "scenario": scenario,
                        "map": md.name,
                        "si": si,
                        "gi": gi,
                        "time_us": f"{us:.1f}",
                        "reachable": 1,
                        "reached_goal": reached,
                        "opt_ratio": opt,
                        "first_move_correct": fm,
                    }
                    writer.writerow(row)
                    if "excl precomp" in algo_name:
                        hpa_excl_rows.append(row)

                done += 1
                progress_bar(done, total_work, prefix=prefix)

    if hpa_excl_rows and hpa_precomp_times:
        avg_precomp = sum(hpa_precomp_times) / len(hpa_precomp_times)
        amortized = avg_precomp / N_PAIRS
        for orig in hpa_excl_rows:
            row = dict(orig)
            row["algo"] = "hpa* incl precomp"
            row["time_us"] = f"{float(str(orig['time_us'])) + amortized:.1f}"
            writer.writerow(row)

    out_f.close()
    print(f"\nSaved {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
