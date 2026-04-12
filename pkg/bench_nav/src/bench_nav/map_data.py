from __future__ import annotations

import heapq
from pathlib import Path

from proto.cambc_pb2 import Map

from bench_nav.common import CE, CR, DIR8, INF


def load_map(path: str | Path) -> Map:
    m = Map()
    m.ParseFromString(Path(path).read_bytes())
    return m


def build_cost(tiles: list[int], n: int) -> list[int]:
    return [INF if tiles[i] in (1, 2, 3) else CE for i in range(n)]


def build_nb(w: int, h: int) -> list[list[int]]:
    n = w * h
    nb: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append(ny * w + nx)
    return nb


def build_pnb(nb: list[list[int]], cost: list[int]) -> list[list[int]]:
    return [[ni for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))]


def build_pnbc(nb: list[list[int]], cost: list[int]) -> list[list[tuple[int, int]]]:
    return [[(ni, cost[ni]) for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))]


def build_pnb_navbfs(
    w: int, h: int, cost: list[int]
) -> tuple[list[list[int]], list[list[int]]]:
    n = w * h
    push: list[list[int]] = [[] for _ in range(n)]
    aset: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        if cost[i] >= INF:
            continue
        cx, cy = i % w, i // w
        has_ne = cy > 0 and cx < w - 1 and cost[(cy - 1) * w + (cx + 1)] < INF
        has_se = cy < h - 1 and cx < w - 1 and cost[(cy + 1) * w + (cx + 1)] < INF
        has_sw = cy < h - 1 and cx > 0 and cost[(cy + 1) * w + (cx - 1)] < INF
        has_nw = cy > 0 and cx > 0 and cost[(cy - 1) * w + (cx - 1)] < INF
        if has_ne:
            push[i].append((cy - 1) * w + (cx + 1))
        if has_se:
            push[i].append((cy + 1) * w + (cx + 1))
        if has_sw:
            push[i].append((cy + 1) * w + (cx - 1))
        if has_nw:
            push[i].append((cy - 1) * w + (cx - 1))
        if cy > 0 and cost[(cy - 1) * w + cx] < INF:  # N
            (aset if has_ne and has_nw else push)[i].append((cy - 1) * w + cx)
        if cx < w - 1 and cost[cy * w + (cx + 1)] < INF:  # E
            (aset if has_ne and has_se else push)[i].append(cy * w + (cx + 1))
        if cy < h - 1 and cost[(cy + 1) * w + cx] < INF:  # S
            (aset if has_se and has_sw else push)[i].append((cy + 1) * w + cx)
        if cx > 0 and cost[cy * w + (cx - 1)] < INF:  # W
            (aset if has_sw and has_nw else push)[i].append(cy * w + (cx - 1))
    return push, aset


def build_pnb_dual(
    nb: list[list[int]], cost: list[int]
) -> tuple[list[list[int]], list[list[int]]]:
    n = len(nb)
    pnb1: list[list[int]] = [[] for _ in range(n)]
    pnb3: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for ni in nb[i]:
            c = cost[ni]
            if c == CR:
                pnb1[i].append(ni)
            elif c == CE:
                pnb3[i].append(ni)
    return pnb1, pnb3


def place_roads(
    tiles: list[int],
    cost: list[int],
    nb: list[list[int]],
    passable: list[int],
) -> int:
    n = len(tiles)
    ores: list[int] = [i for i in range(n) if tiles[i] in (2, 3)]
    ore_adj: set[int] = set()
    for oi in ores:
        for ni in nb[oi]:
            if cost[ni] < INF:
                ore_adj.add(ni)
    targets = list(ore_adj)[:5]
    core_i = passable[0] if passable else 0
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
    return len(roads)
