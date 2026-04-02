"""Unified navigation benchmark.

Runs all pathfinding algorithms across all 38 known maps, 200 random pairs each.
No dependency on bots/ or cambc. Only needs proto/cambc_pb2.py for map loading
and bots/intgrah/v50/algorithms/hpastar.py (imported by path).

Usage:
    python scripts/bench_nav.py
    pypy scripts/bench_nav.py
"""

from __future__ import annotations

import argparse
import csv
import gc
import heapq
import random
import sys
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from scripts.hpastar import GatewayGraph
from scripts.replay import load_map

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
    m = load_map(path)
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
        "pnb",
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
        self.pnb: list[list[int]] = _build_pnb(self.nb, self.cost)
        self.passable: list[int] = [i for i in range(self.n) if self.cost[i] < INF]
        self.offsets_card: tuple[int, ...] = (-self.w, -1, 1, self.w)
        w = self.w
        self.offsets_diag: tuple[int, ...] = (-w - 1, -w + 1, w - 1, w + 1)
        self.apsp: ApspTable | None = None
        self.hpa_graph: GatewayGraph | None = None

    def reset_cost_no_roads(self) -> None:
        self.cost = [INF if self.tiles[i] in (1, 2, 3) else CE for i in range(self.n)]
        self.pnb = _build_pnb(self.nb, self.cost)
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
        self.pnb = _build_pnb(self.nb, cost)
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


def _build_pnb(nb: list[list[int]], cost: list[int]) -> list[list[int]]:
    return [[ni for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))]


# ---------------------------------------------------------------------------
# Ground truth: full Dijkstra + all optimal first moves
# ---------------------------------------------------------------------------


def dijkstra_full(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni in nb[node]:
            c = cost[ni]
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
    cost, nb = md.cost, md.pnb
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
            if dist[ni] + c == dist[node]:
                on_shortest[ni] = True
                q.append(ni)
    moves: set[int] = set()
    for ni in nb[si]:
        if not on_shortest[ni]:
            continue
        c = cost[ni]
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
    w, n, cost, nb = md.w, md.n, md.cost, md.pnb
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
    w, n, cost, nb = md.w, md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    gx, gy = gi % w, gi // w
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
        for ni in nb[node]:
            c = cost[ni]
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


def algo_bfs(md: MapData, si: int, gi: int) -> Path_:
    n, cost, nb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    found = False
    while q:
        node = q.popleft()
        for ni in nb[node]:
            if parent[ni] != -1:
                continue
            parent[ni] = node
            if ni == gi:
                found = True
                break
            q.append(ni)
        if found:
            break
    if not found:
        return None
    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    return path


def algo_bfs_expand(md: MapData, si: int, gi: int) -> Path_:
    n, cost, nb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    n2 = n + n
    parent: list[int] = [-1] * (n + n2)
    parent[si] = si
    q: deque[int] = deque([si])
    found = False
    while q:
        node = q.popleft()
        if node < n:
            for ni in nb[node]:
                c = cost[ni]
                if c == CR:
                    if parent[ni] != -1:
                        continue
                    parent[ni] = node
                    if ni == gi:
                        found = True
                        break
                    q.append(ni)
                else:
                    vi = ni + n2
                    if parent[vi] != -1:
                        continue
                    parent[vi] = node
                    q.append(vi)
        elif node >= n2:
            ni = node - n
            if parent[ni] != -1:
                continue
            parent[ni] = node
            q.append(ni)
        else:
            ni = node - n
            if parent[ni] != -1:
                continue
            parent[ni] = node
            if ni < n and ni == gi:
                found = True
                break
            q.append(ni)
        if found:
            break
    if not found:
        return None
    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur % n)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    i = 1
    while i < len(path):
        if path[i] == path[i - 1]:
            path.pop(i)
        else:
            i += 1
    return path


def algo_bfs_roadopt(md: MapData, si: int, gi: int) -> Path_:
    n, cost, nb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    found = False
    while q:
        node = q.popleft()
        for ni in nb[node]:
            if parent[ni] != -1:
                continue
            parent[ni] = node
            if ni == gi:
                found = True
                break
            q.append(ni)
        if found:
            break
    if not found:
        return None
    path: list[int] = []
    cur = gi
    while cur != si:
        path.append(cur)
        cur = parent[cur]
    path.append(si)
    path.reverse()
    if len(path) < 3:
        return path
    next_next = path[2]
    best_ni = path[1]
    best_cost = cost[best_ni]
    for ni in nb[si]:
        if cost[ni] >= best_cost or parent[ni] != si:
            continue
        adjacent_to_next = False
        for ni2 in nb[ni]:
            if ni2 == next_next:
                adjacent_to_next = True
                break
        if adjacent_to_next:
            best_ni = ni
            best_cost = cost[ni]
    path[1] = best_ni
    return path


def algo_bibfs(md: MapData, si: int, gi: int) -> Path_:
    n, cost, nb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    parent_f: list[int] = [-1] * n
    parent_b: list[int] = [-1] * n
    dist_f: list[int] = [INF] * n
    dist_b: list[int] = [INF] * n
    parent_f[si] = si
    parent_b[gi] = gi
    dist_f[si] = 0
    dist_b[gi] = 0
    qf: deque[int] = deque([si])
    qb: deque[int] = deque([gi])
    best = INF
    meet = -1
    while qf or qb:
        min_remaining = 0
        if qf:
            min_remaining += dist_f[qf[0]]
        if qb:
            min_remaining += dist_b[qb[0]]
        if min_remaining >= best:
            break
        if qf and (not qb or len(qf) <= len(qb)):
            node = qf.popleft()
            d = dist_f[node] + 1
            for ni in nb[node]:
                if dist_f[ni] <= d:
                    continue
                dist_f[ni] = d
                parent_f[ni] = node
                qf.append(ni)
                if dist_b[ni] < INF and d + dist_b[ni] < best:
                    best = d + dist_b[ni]
                    meet = ni
        elif qb:
            node = qb.popleft()
            d = dist_b[node] + 1
            for ni in nb[node]:
                if dist_b[ni] <= d:
                    continue
                dist_b[ni] = d
                parent_b[ni] = node
                qb.append(ni)
                if dist_f[ni] < INF and dist_f[ni] + d < best:
                    best = dist_f[ni] + d
                    meet = ni
    if meet < 0:
        return None
    path: list[int] = []
    cur = meet
    while cur != si:
        path.append(cur)
        cur = parent_f[cur]
    path.append(si)
    path.reverse()
    if meet != gi:
        cur = parent_b[meet]
        while cur != gi:
            path.append(cur)
            cur = parent_b[cur]
        path.append(gi)
    return path


def algo_gbfs(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    w, n, cost, nb = md.w, md.n, md.cost, md.pnb
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
    n, cost, nb = md.n, md.cost, md.pnb
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
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                heapq.heappush(heap, (nd, ni))
    return _extract(parent, si, last_node)


def algo_dijkstra_bucket(md: MapData, si: int, gi: int, budget: int = 0) -> Path_:
    n, cost, nb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
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
        for ni in nb[node]:
            c = cost[ni]
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
    n, cost, nb = md.n, md.cost, md.pnb
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


def validate_path(md: MapData, path: list[int], si: int, algo_name: str) -> bool:
    if not path:
        return True
    w, n, cost = md.w, md.n, md.cost
    if path[0] != si:
        print(
            f"INVALID {algo_name} on {md.name}: start={path[0]} expected={si}",
            file=sys.stderr,
        )
        return False
    for k, node in enumerate(path):
        if node < 0 or node >= n:
            print(
                f"INVALID {algo_name} on {md.name}: node {k} out of bounds: {node}",
                file=sys.stderr,
            )
            return False
        if k > 0 and cost[node] >= INF:
            print(
                f"INVALID {algo_name} on {md.name}: node {k} impassable: {node}",
                file=sys.stderr,
            )
            return False
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        dx = abs(a % w - b % w)
        dy = abs(a // w - b // w)
        if dx > 1 or dy > 1:
            print(
                f"INVALID {algo_name} on {md.name}: non-adjacent step {k}: "
                f"({a % w},{a // w})->({b % w},{b // w})",
                file=sys.stderr,
            )
            return False
    return True


# ---------------------------------------------------------------------------
# Algorithm registry
# ---------------------------------------------------------------------------


def _make_algos() -> list[AlgoEntry]:
    algos: list[AlgoEntry] = []

    algos.extend(
        (
            f"astar heap cheb w={w}",
            lambda md, si, gi, _w=w: algo_astar_heap(md, si, gi, weight=_w),
            False,
        )
        for w in [1, 3]
    )

    algos.extend(
        (
            f"astar bucket cheb w={w}",
            lambda md, si, gi, _w=w: algo_astar_bucket(md, si, gi, weight=_w),
            False,
        )
        for w in [1, 3]
    )

    algos.append(("astar heap apsp", algo_astar_apsp, True))
    algos.append(("bfs", algo_bfs, False))
    algos.append(("bfs expand", algo_bfs_expand, False))
    algos.append(("bfs roadopt", algo_bfs_roadopt, False))
    algos.append(("bibfs", algo_bibfs, False))
    algos.append(("gbfs", algo_gbfs, False))
    algos.append(("dijkstra heap", algo_dijkstra_heap, False))
    algos.append(("dijkstra bucket", algo_dijkstra_bucket, False))
    algos.append(("hpastar excl precomp", algo_hpa, True))

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
    parser = argparse.ArgumentParser(description="Navigation benchmark")
    parser.add_argument(
        "--algos",
        nargs="*",
        help="Algorithm name substrings to include (default: all). "
        "E.g. --algos bfs 'astar heap'",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available algorithms and exit",
    )
    args = parser.parse_args()

    if args.list:
        for name, _, _ in ALGOS:
            print(name)
        sys.exit(0)

    if args.algos:
        selected = [
            (name, fn, req)
            for name, fn, req in ALGOS
            if any(pat in name for pat in args.algos)
        ]
        if not selected:
            print("No algorithms matched. Use --list to see names.", file=sys.stderr)
            sys.exit(1)
    else:
        selected = list(ALGOS)

    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_maps = len(map_files)
    needs_apsp = any(req for _, _, req in selected)
    needs_hpa = any("hpa" in name for name, _, _ in selected)
    n_algos = len(selected)
    n_scenarios = len(SCENARIOS)
    total_work = n_maps * n_scenarios * (n_algos + 1)
    done = 0

    out_path = Path(__file__).resolve().parent / "bench_nav.csv"
    out_f = out_path.open("w", newline="")
    writer = csv.DictWriter(out_f, fieldnames=CSV_FIELDS)
    writer.writeheader()

    hpa_precomp_times: list[float] = []

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

            for algo_name, algo_fn, req_apsp in selected:
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
                        continue

                    t0 = time.perf_counter()
                    path = algo_fn(md, si, gi)
                    us = (time.perf_counter() - t0) * 1e6

                    reached = 0
                    opt = ""
                    fm = 0
                    if path is not None and len(path) >= 1:
                        validate_path(md, path, si, algo_name)
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

                done += 1
                progress_bar(done, total_work, prefix=prefix)

    if hpa_precomp_times:
        hpa_precomp_times.sort()
        hn = len(hpa_precomp_times)
        print(
            f"\nHPA* precomp: p50={hpa_precomp_times[hn // 2]:.0f}us"
            f" p100={hpa_precomp_times[-1]:.0f}us",
            file=sys.stderr,
        )

    out_f.close()
    print(f"\nSaved {out_path}", file=sys.stderr)


def sssp_bfs(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        for ni in nb[node]:
            if parent[ni] != -1:
                continue
            parent[ni] = node
            q.append(ni)
    return parent


def sssp_bfs_expand(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    n2 = n + n
    parent: list[int] = [-1] * (n + n2)
    parent[si] = si
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        if node < n:
            for ni in nb[node]:
                c = cost[ni]
                if c == CR:
                    if parent[ni] != -1:
                        continue
                    parent[ni] = node
                    q.append(ni)
                else:
                    vi = ni + n2
                    if parent[vi] != -1:
                        continue
                    parent[vi] = node
                    q.append(vi)
        elif node >= n2:
            ni = node - n
            if parent[ni] != -1:
                continue
            parent[ni] = node
            q.append(ni)
        else:
            ni = node - n
            if parent[ni] != -1:
                continue
            parent[ni] = node
            q.append(ni)
    return parent


def sssp_dijkstra_heap(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni in nb[node]:
            c = cost[ni]
            nd = d + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                heapq.heappush(heap, (nd, ni))
    return parent


def sssp_dijkstra_bucket(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    mod = CE + 1
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
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
        gn = dist[node]
        for ni in nb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[nd % mod].append(ni)
    return parent


def sssp_dijkstra_bucket_inline(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    bk: list[deque[int]] = [deque() for _ in range(4)]
    bk[0].append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        if not bk[bi]:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bk[bi].popleft()
        if dist[node] != cur_d:
            continue
        gn = cur_d
        for ni in nb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                bk[nd & 3].append(ni)
    return parent


def sssp_dijkstra_bucket_unrolled(md: MapData, si: int) -> list[int]:
    n, cost, nb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    parent: list[int] = [-1] * n
    dist[si] = 0
    parent[si] = si
    bk0: deque[int] = deque()
    bk1: deque[int] = deque()
    bk2: deque[int] = deque()
    bk3: deque[int] = deque()
    bk0.append(si)
    cur_d = 0
    emp = 0
    while emp < 4:
        bi = cur_d & 3
        if bi == 0:
            bk = bk0
        elif bi == 1:
            bk = bk1
        elif bi == 2:
            bk = bk2
        else:
            bk = bk3
        if not bk:
            cur_d += 1
            emp += 1
            continue
        emp = 0
        node = bk.popleft()
        if dist[node] != cur_d:
            continue
        gn = cur_d
        for ni in nb[node]:
            c = cost[ni]
            nd = gn + c
            if nd < dist[ni]:
                dist[ni] = nd
                parent[ni] = node
                r = nd & 3
                if r == 0:
                    bk0.append(ni)
                elif r == 1:
                    bk1.append(ni)
                elif r == 2:
                    bk2.append(ni)
                else:
                    bk3.append(ni)
    return parent


type SsspFn = Callable[[MapData, int], list[int]]

SSSP_ALGOS: list[tuple[str, SsspFn]] = [
    ("bfs", sssp_bfs),
    ("bfs expand", sssp_bfs_expand),
    ("dijkstra heap", sssp_dijkstra_heap),
    ("dijkstra bucket", sssp_dijkstra_bucket),
    ("dijkstra bucket inline", sssp_dijkstra_bucket_inline),
    ("dijkstra bucket unrolled", sssp_dijkstra_bucket_unrolled),
]


def bench_sssp() -> None:
    parser = argparse.ArgumentParser(description="SSSP benchmark")
    parser.add_argument(
        "--algos",
        nargs="*",
        help="Algorithm name substrings to include (default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available algorithms and exit",
    )
    args = parser.parse_args()

    if args.list:
        for name, _ in SSSP_ALGOS:
            print(name)
        sys.exit(0)

    if args.algos:
        selected = [
            (name, fn)
            for name, fn in SSSP_ALGOS
            if any(pat in name for pat in args.algos)
        ]
        if not selected:
            print("No algorithms matched. Use --list to see names.", file=sys.stderr)
            sys.exit(1)
    else:
        selected = list(SSSP_ALGOS)

    map_files = sorted(MAPS_DIR.glob("*.map26"))
    if not map_files:
        print(f"No .map26 files in {MAPS_DIR}", file=sys.stderr)
        sys.exit(1)

    n_sources = 500
    times: dict[str, dict[str, list[float]]] = {
        name: {} for name, _ in selected
    }

    for mf in map_files:
        md = MapData(mf)
        if not md.passable:
            continue

        rng = random.Random(SEED)
        sources = [rng.choice(md.passable) for _ in range(n_sources)]

        for scenario in SCENARIOS:
            md.reset_cost_no_roads()
            if scenario == "with_roads":
                md.place_roads()

            label = f"{md.name}/{scenario}"
            sys.stderr.write(f"\r{label:40s}")
            sys.stderr.flush()

            for algo_name, algo_fn in selected:
                gc.disable()
                for si in sources:
                    t0 = time.perf_counter()
                    algo_fn(md, si)
                    us = (time.perf_counter() - t0) * 1e6
                    times[algo_name].setdefault(scenario, []).append(us)
                gc.enable()

    sys.stderr.write("\r" + " " * 60 + "\r")

    for scenario in SCENARIOS:
        print(f"\n  {scenario.upper()}")
        print(f"  {'Algorithm':<24s} {'p50':>8s} {'p90':>8s} {'p99':>8s} {'p100':>8s}")
        print(f"  {'-' * 56}")
        for algo_name, _ in selected:
            ts = sorted(times[algo_name].get(scenario, []))
            if not ts:
                continue
            nt = len(ts)
            p50 = ts[nt // 2]
            p90 = ts[int(nt * 0.9)]
            p99 = ts[int(nt * 0.99)]
            p100 = ts[-1]
            print(f"  {algo_name:<24s} {p50:>7.0f}us {p90:>7.0f}us {p99:>7.0f}us {p100:>7.0f}us")


if __name__ == "__main__":
    main()
