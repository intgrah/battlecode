from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from bench_nav.common import CE, CR, INF, Path_

if TYPE_CHECKING:
    from bench_nav.map_data import MapData


def spsp_biastar_dial_cheb(md: MapData, si: int, gi: int) -> Path_:
    """Bidirectional A* with Dial's buckets and Chebyshev heuristic.

    Optimal stopping: track μ = best known path cost, stop when
    min(cur_f_forward, cur_f_backward) ≥ μ.  Guarantees shortest path
    with consistent heuristics.

    Backward search uses the reverse graph where edge cost from node to
    any neighbor = cost[node] (destination cost in forward = source cost
    in reverse).
    """
    w, n, cost, pnb = md.w, md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    sx, sy = si % w, si // w
    gx, gy = gi % w, gi // w
    mod = CE + 2  # max Δf per step = CE + 1

    # Forward search: si → gi
    g_f: list[int] = [INF] * n
    parent_f: list[int] = [-1] * n
    g_f[si] = 0
    parent_f[si] = si
    h0 = max(abs(sx - gx), abs(sy - gy)) * CR
    bk_f: list[deque[int]] = [deque() for _ in range(mod)]
    bk_f[h0 % mod].append(si)
    cf = h0
    ef = 0

    # Backward search: gi → si on reverse graph
    g_b: list[int] = [INF] * n
    parent_b: list[int] = [-1] * n
    g_b[gi] = 0
    parent_b[gi] = gi
    bk_b: list[deque[int]] = [deque() for _ in range(mod)]
    bk_b[h0 % mod].append(gi)
    cb = h0
    eb = 0

    best = INF
    meet = -1

    while ef < mod or eb < mod:
        if cf >= best and cb >= best:
            break

        if ef < mod and (eb >= mod or cf <= cb):
            # Forward step
            bi = cf % mod
            if not bk_f[bi]:
                cf += 1
                ef += 1
                continue
            ef = 0
            node = bk_f[bi].popleft()
            nx, ny = node % w, node // w
            h_node = max(abs(nx - gx), abs(ny - gy)) * CR
            if g_f[node] + h_node != cf:
                continue
            gn = g_f[node]
            # Check meeting at expansion
            if g_b[node] < INF:
                cand = gn + g_b[node]
                if cand < best:
                    best = cand
                    meet = node
            for ni in pnb[node]:
                c = cost[ni]
                nd = gn + c
                if nd < g_f[ni]:
                    g_f[ni] = nd
                    parent_f[ni] = node
                    nix, niy = ni % w, ni // w
                    h_ni = max(abs(nix - gx), abs(niy - gy)) * CR
                    bk_f[(nd + h_ni) % mod].append(ni)
                    # Check meeting at relaxation
                    if g_b[ni] < INF:
                        cand = nd + g_b[ni]
                        if cand < best:
                            best = cand
                            meet = ni
        elif eb < mod:
            # Backward step (reverse graph: edge cost from node = cost[node])
            bi = cb % mod
            if not bk_b[bi]:
                cb += 1
                eb += 1
                continue
            eb = 0
            node = bk_b[bi].popleft()
            nx, ny = node % w, node // w
            h_node = max(abs(nx - sx), abs(ny - sy)) * CR
            if g_b[node] + h_node != cb:
                continue
            gn = g_b[node]
            # Check meeting at expansion
            if g_f[node] < INF:
                cand = g_f[node] + gn
                if cand < best:
                    best = cand
                    meet = node
            c_node = cost[node]
            for ni in pnb[node]:
                nd = gn + c_node
                if nd < g_b[ni]:
                    g_b[ni] = nd
                    parent_b[ni] = node
                    nix, niy = ni % w, ni // w
                    h_ni = max(abs(nix - sx), abs(niy - sy)) * CR
                    bk_b[(nd + h_ni) % mod].append(ni)
                    # Check meeting at relaxation
                    if g_f[ni] < INF:
                        cand = g_f[ni] + nd
                        if cand < best:
                            best = cand
                            meet = ni
        else:
            break

    if meet < 0:
        return None

    # Extract path: si → meet via parent_f, meet → gi via parent_b
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


def spsp_biastar_dial_cheb_ft(md: MapData, si: int, gi: int) -> Path_:
    """Bidirectional A* with Dial's buckets and Chebyshev heuristic.

    First-touch stopping: return immediately when a node expanded by one
    direction has already been reached by the other.  Fast but NOT optimal —
    the meeting node's g-value from the non-expanding side may not be settled.
    """
    w, n, cost, pnb = md.w, md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    sx, sy = si % w, si // w
    gx, gy = gi % w, gi // w
    mod = CE + 2  # max Δf per step = CE + 1

    # Forward search: si → gi
    g_f: list[int] = [INF] * n
    parent_f: list[int] = [-1] * n
    g_f[si] = 0
    parent_f[si] = si
    h0 = max(abs(sx - gx), abs(sy - gy)) * CR
    bk_f: list[deque[int]] = [deque() for _ in range(mod)]
    bk_f[h0 % mod].append(si)
    cf = h0
    ef = 0

    # Backward search: gi → si on reverse graph
    g_b: list[int] = [INF] * n
    parent_b: list[int] = [-1] * n
    g_b[gi] = 0
    parent_b[gi] = gi
    bk_b: list[deque[int]] = [deque() for _ in range(mod)]
    bk_b[h0 % mod].append(gi)
    cb = h0
    eb = 0

    meet = -1

    while ef < mod or eb < mod:
        if ef < mod and (eb >= mod or cf <= cb):
            # Forward step
            bi = cf % mod
            if not bk_f[bi]:
                cf += 1
                ef += 1
                continue
            ef = 0
            node = bk_f[bi].popleft()
            nx, ny = node % w, node // w
            h_node = max(abs(nx - gx), abs(ny - gy)) * CR
            if g_f[node] + h_node != cf:
                continue
            # First-touch: expanded by forward, reached by backward?
            if g_b[node] < INF:
                meet = node
                break
            gn = g_f[node]
            for ni in pnb[node]:
                nd = gn + cost[ni]
                if nd < g_f[ni]:
                    g_f[ni] = nd
                    parent_f[ni] = node
                    nix, niy = ni % w, ni // w
                    h_ni = max(abs(nix - gx), abs(niy - gy)) * CR
                    bk_f[(nd + h_ni) % mod].append(ni)
        elif eb < mod:
            # Backward step (reverse graph: edge cost from node = cost[node])
            bi = cb % mod
            if not bk_b[bi]:
                cb += 1
                eb += 1
                continue
            eb = 0
            node = bk_b[bi].popleft()
            nx, ny = node % w, node // w
            h_node = max(abs(nx - sx), abs(ny - sy)) * CR
            if g_b[node] + h_node != cb:
                continue
            # First-touch: expanded by backward, reached by forward?
            if g_f[node] < INF:
                meet = node
                break
            gn = g_b[node]
            c_node = cost[node]
            for ni in pnb[node]:
                nd = gn + c_node
                if nd < g_b[ni]:
                    g_b[ni] = nd
                    parent_b[ni] = node
                    nix, niy = ni % w, ni // w
                    h_ni = max(abs(nix - sx), abs(niy - sy)) * CR
                    bk_b[(nd + h_ni) % mod].append(ni)
        else:
            break

    if meet < 0:
        return None

    # Extract path: si → meet via parent_f, meet → gi via parent_b
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


def spsp_astar_dial_cheb_bw_dijkstra(md: MapData, si: int, gi: int) -> Path_:
    """Forward A* (Dial's, Chebyshev) + backward Dijkstra (Dial's, no heuristic).

    Asymmetric bidirectional search. Forward uses A* with Chebyshev heuristic
    toward the goal. Backward uses plain Dijkstra from the goal (no heuristic),
    expanding in order of true distance from the goal.

    Optimal stopping: stop when min(cur_f_forward, cur_d_backward) >= mu.
    """
    w, n, cost, pnb = md.w, md.n, md.cost, md.pnb
    if si == gi:
        return [si]
    sx, sy = si % w, si // w
    gx, gy = gi % w, gi // w
    mod_f = CE + 2
    mod_b = CE + 1

    g_f: list[int] = [INF] * n
    parent_f: list[int] = [-1] * n
    g_f[si] = 0
    parent_f[si] = si
    h0 = max(abs(sx - gx), abs(sy - gy)) * CR
    bk_f: list[deque[int]] = [deque() for _ in range(mod_f)]
    bk_f[h0 % mod_f].append(si)
    cf = h0
    ef = 0

    g_b: list[int] = [INF] * n
    parent_b: list[int] = [-1] * n
    g_b[gi] = 0
    parent_b[gi] = gi
    bk_b: list[deque[int]] = [deque() for _ in range(mod_b)]
    bk_b[0].append(gi)
    cb = 0
    eb = 0

    best = INF
    meet = -1

    while ef < mod_f or eb < mod_b:
        if cf >= best and cb >= best:
            break

        if ef < mod_f and (eb >= mod_b or cf <= cb):
            bi = cf % mod_f
            if not bk_f[bi]:
                cf += 1
                ef += 1
                continue
            ef = 0
            node = bk_f[bi].popleft()
            nx, ny = node % w, node // w
            h_node = max(abs(nx - gx), abs(ny - gy)) * CR
            if g_f[node] + h_node != cf:
                continue
            gn = g_f[node]
            if g_b[node] < INF:
                cand = gn + g_b[node]
                if cand < best:
                    best = cand
                    meet = node
            for ni in pnb[node]:
                nd = gn + cost[ni]
                if nd < g_f[ni]:
                    g_f[ni] = nd
                    parent_f[ni] = node
                    nix, niy = ni % w, ni // w
                    h_ni = max(abs(nix - gx), abs(niy - gy)) * CR
                    bk_f[(nd + h_ni) % mod_f].append(ni)
                    if g_b[ni] < INF:
                        cand = nd + g_b[ni]
                        if cand < best:
                            best = cand
                            meet = ni
        elif eb < mod_b:
            bi = cb % mod_b
            if not bk_b[bi]:
                cb += 1
                eb += 1
                continue
            eb = 0
            node = bk_b[bi].popleft()
            if g_b[node] != cb:
                continue
            gn = g_b[node]
            if g_f[node] < INF:
                cand = g_f[node] + gn
                if cand < best:
                    best = cand
                    meet = node
            c_node = cost[node]
            for ni in pnb[node]:
                nd = gn + c_node
                if nd < g_b[ni]:
                    g_b[ni] = nd
                    parent_b[ni] = node
                    bk_b[nd % mod_b].append(ni)
                    if g_f[ni] < INF:
                        cand = g_f[ni] + nd
                        if cand < best:
                            best = cand
                            meet = ni
        else:
            break

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
