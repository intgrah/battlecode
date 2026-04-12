from __future__ import annotations

import heapq
import sys
from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import INF

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def dijkstra_full(md: MapData, si: int) -> list[int]:
    """Reference implementation to compare ground truth"""
    n, cost, pnb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni in pnb[node]:
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
    cost, pnb = md.cost, md.pnb
    n = md.n
    on_shortest: list[bool] = [False] * n
    on_shortest[gi] = True
    q: deque[int] = deque([gi])
    while q:
        node = q.popleft()
        for ni in pnb[node]:
            if on_shortest[ni]:
                continue
            c = cost[node]
            if dist[ni] + c == dist[node]:
                on_shortest[ni] = True
                q.append(ni)
    moves: set[int] = set()
    for ni in pnb[si]:
        if not on_shortest[ni]:
            continue
        c = cost[ni]
        if dist[si] + c == dist[ni]:
            moves.add(ni)
    return moves


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


def extract_path_from_dist(
    dist: list[int],
    cost: list[int],
    pnb: list[list[int]],
    si: int,
    gi: int,
) -> list[int] | None:
    if dist[gi] >= INF:
        return None
    if si == gi:
        return [si]
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        for ni in pnb[cur]:
            if dist[ni] + cost[cur] == d:
                path.append(ni)
                cur = ni
                break
        else:
            return None
    path.reverse()
    return path


def sssp_reference_dist(md: MapData, si: int) -> list[int]:
    n, cost, pnb = md.n, md.cost, md.pnb
    dist: list[int] = [INF] * n
    dist[si] = 0
    heap: list[tuple[int, int]] = [(0, si)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for ni in pnb[node]:
            nd = d + cost[ni]
            if nd < dist[ni]:
                dist[ni] = nd
                heapq.heappush(heap, (nd, ni))
    return dist


def parent_to_dist(parent: list[int], cost: list[int], n: int, si: int) -> list[int]:
    children: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        p = parent[i]
        if p not in (-1, i):
            children[p].append(i)
    dist: list[int] = [INF] * n
    dist[si] = 0
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        for child in children[node]:
            dist[child] = dist[node] + cost[child]
            q.append(child)
    return dist


def expanded_parent_to_dist(
    parent: list[int],
    n: int,
    si: int,
) -> list[int]:
    total = len(parent)
    children: list[list[int]] = [[] for _ in range(total)]
    for i in range(total):
        p = parent[i]
        if p not in (-1, i):
            children[p].append(i)
    full_dist: list[int] = [INF] * total
    full_dist[si] = 0
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        for child in children[node]:
            full_dist[child] = full_dist[node] + 1
            q.append(child)
    dist: list[int] = [INF] * n
    dist[si] = 0
    for i in range(n):
        if full_dist[i] < INF:
            dist[i] = full_dist[i]
    return dist
