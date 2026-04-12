from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import CR, INF, Path_

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def spsp_bfs(md: MapData, si: int, gi: int) -> Path_:
    n, pnb = md.n, md.pnb
    if si == gi:
        return [si]
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    found = False
    while q:
        node = q.popleft()
        for ni in pnb[node]:
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


def spsp_bfs_expand(md: MapData, si: int, gi: int) -> Path_:
    n, cost, pnb = md.n, md.cost, md.pnb
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
            for ni in pnb[node]:
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


def spsp_bfs_roadopt(md: MapData, si: int, gi: int) -> Path_:
    n, cost, pnb = md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    parent: list[int] = [-1] * n
    parent[si] = si
    q: deque[int] = deque([si])
    found = False
    while q:
        node = q.popleft()
        for ni in pnb[node]:
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
    for ni in pnb[si]:
        if cost[ni] >= best_cost or parent[ni] != si:
            continue
        adjacent_to_next = False
        for ni2 in pnb[ni]:
            if ni2 == next_next:
                adjacent_to_next = True
                break
        if adjacent_to_next:
            best_ni = ni
            best_cost = cost[ni]
    path[1] = best_ni
    return path


def spsp_navbfs(md: MapData, si: int, gi: int) -> Path_:
    """Mirrors bots/adgato/bfs_test/bfs.py::_bfs_compute.

    Uses precomputed pnb_push/pnb_set split: cardinals bracketed by two
    passable diagonals don't get enqueued (they're reached one level later
    via the diagonal expansion). dist initialized to INF, fused visited
    check, growable queue iterated with `for node in q`.
    """
    n = md.n
    pnb_push = md.pnb_navbfs_push
    pnb_set = md.pnb_navbfs_set
    if si == gi:
        return [si]
    pnb = md.pnb
    dist: list[int] = [INF] * n
    dist[si] = 0
    q: list[int] = [si]
    stop_at = INF
    for node in q:
        d = dist[node] + 1
        if node == gi:
            stop_at = d
        if d > stop_at:
            break
        for ni in pnb_push[node]:
            if d < dist[ni]:
                dist[ni] = d
                q.append(ni)
        for ni in pnb_set[node]:
            if d < dist[ni]:
                if ni == gi:
                    stop_at = d + 1
                dist[ni] = d
    if dist[gi] >= INF:
        return None
    cost = md.cost
    path = [gi]
    cur = gi
    while cur != si:
        d = dist[cur]
        best = -1
        best_cost = INF + 1
        for ni in pnb[cur]:
            if dist[ni] == d - 1 and cost[ni] < best_cost:
                best = ni
                best_cost = cost[ni]
        if best == -1:
            return None
        path.append(best)
        cur = best
    path.reverse()
    return path


def spsp_navbfs_noextract(md: MapData, si: int, gi: int) -> Path_:
    n = md.n
    pnb_push = md.pnb_navbfs_push
    pnb_set = md.pnb_navbfs_set
    if si == gi:
        return [si]
    dist: list[int] = [INF] * n
    dist[si] = 0
    q: list[int] = [si]
    stop_at = INF
    for node in q:
        d = dist[node] + 1
        if node == gi:
            stop_at = d
        if d > stop_at:
            break
        for ni in pnb_push[node]:
            if d < dist[ni]:
                dist[ni] = d
                q.append(ni)
        for ni in pnb_set[node]:
            if d < dist[ni]:
                if ni == gi:
                    stop_at = d + 1
                dist[ni] = d
    return None


def spsp_bibfs(md: MapData, si: int, gi: int) -> Path_:
    n, pnb = md.n, md.pnb
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
            for ni in pnb[node]:
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
            for ni in pnb[node]:
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
