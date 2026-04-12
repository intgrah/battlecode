from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def sssp_bfs(md: MapData, si: int) -> list[int]:
    n, pnb = md.n, md.pnb
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        for ni in pnb[node]:
            if parent[ni] != -1:
                continue
            parent[ni] = node
            q.append(ni)
    return parent


def sssp_bfs_expand(md: MapData, si: int) -> list[int]:
    n, cost, pnb = md.n, md.cost, md.pnb
    n2 = n + n
    parent: list[int] = [-1] * (n + n2)
    parent[si] = si
    q: deque[int] = deque([si])
    while q:
        node = q.popleft()
        if node < n:
            for ni in pnb[node]:
                c = cost[ni]
                if c == 1:
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
