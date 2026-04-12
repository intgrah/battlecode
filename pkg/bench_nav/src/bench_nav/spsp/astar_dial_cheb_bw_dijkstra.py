from __future__ import annotations

from collections import deque

from bench_nav.common import CE, CR, INF, Path_, extract_parent


def astar_dial_cheb_bw_dijkstra(
    w: int,
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    """Forward A* (Dial's, Chebyshev) + backward Dijkstra (Dial's, no heuristic).

    Asymmetric bidirectional search. Forward uses A* with Chebyshev heuristic
    toward the goal. Backward uses plain Dijkstra from the goal (no heuristic),
    expanding in order of true distance from the goal.

    Optimal stopping: stop when min(cur_f_forward, cur_d_backward) >= mu.
    """
    sx, sy = start % w, start // w
    gx, gy = goal % w, goal // w
    mod_f = CE + 2
    mod_b = CE + 1

    g_f: list[int] = [INF] * n
    parent_f: list[int] = [-1] * n
    g_f[start] = 0
    parent_f[start] = start
    h0 = max(abs(sx - gx), abs(sy - gy)) * CR
    bk_f: list[deque[int]] = [deque() for _ in range(mod_f)]
    bk_f[h0 % mod_f].append(start)
    cf = h0
    ef = 0

    g_b: list[int] = [INF] * n
    parent_b: list[int] = [-1] * n
    g_b[goal] = 0
    parent_b[goal] = goal
    bk_b: list[deque[int]] = [deque() for _ in range(mod_b)]
    bk_b[0].append(goal)
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
            for nb in pnb[node]:
                nd = gn + cost[nb]
                if nd < g_f[nb]:
                    g_f[nb] = nd
                    parent_f[nb] = node
                    nix, niy = nb % w, nb // w
                    h_ni = max(abs(nix - gx), abs(niy - gy)) * CR
                    bk_f[(nd + h_ni) % mod_f].append(nb)
                    if g_b[nb] < INF:
                        cand = nd + g_b[nb]
                        if cand < best:
                            best = cand
                            meet = nb
        elif eb < mod_b:
            bki = bk_b[cb % mod_b]
            if not bki:
                cb += 1
                eb += 1
                continue
            eb = 0
            node = bki.popleft()
            if g_b[node] != cb:
                continue
            gn = g_b[node]
            if g_f[node] < INF:
                cand = g_f[node] + gn
                if cand < best:
                    best = cand
                    meet = node
            c_node = cost[node]
            for nb in pnb[node]:
                nd = gn + c_node
                if nd < g_b[nb]:
                    g_b[nb] = nd
                    parent_b[nb] = node
                    bk_b[nd % mod_b].append(nb)
                    if g_f[nb] < INF:
                        cand = g_f[nb] + nd
                        if cand < best:
                            best = cand
                            meet = nb
        else:
            break

    if meet < 0:
        return None

    path = extract_parent(parent_f, start, meet)
    if path is None:
        return None
    if meet != goal:
        cur = parent_b[meet]
        while cur != goal:
            path.append(cur)
            cur = parent_b[cur]
        path.append(goal)
    return path
