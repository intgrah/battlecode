from collections import deque

from bench_nav.common import CE, CR, INF, Path_, extract_parent


def biastar_dial_cheb(
    w: int,
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    """Bidirectional A* with Dial's buckets and Chebyshev heuristic.

    Optimal stopping: track μ = best known path cost, stop when
    min(cur_f_forward, cur_f_backward) ≥ μ.  Guarantees shortest path
    with consistent heuristics.

    Backward search uses the reverse graph where edge cost from node to
    any neighbor = cost[node] (destination cost in forward = source cost
    in reverse).
    """
    sx, sy = start % w, start // w
    gx, gy = goal % w, goal // w
    mod = CE + 2  # max Δf per step = CE + 1

    # Forward search: start → goal
    g_f: list[int] = [INF] * n
    parent_f: list[int] = [-1] * n
    g_f[start] = 0
    parent_f[start] = start
    h0 = max(abs(sx - gx), abs(sy - gy)) * CR
    bk_f: list[deque[int]] = [deque() for _ in range(mod)]
    bk_f[h0 % mod].append(start)
    cf = h0
    ef = 0

    # Backward search: goal → start on reverse graph
    g_b: list[int] = [INF] * n
    parent_b: list[int] = [-1] * n
    g_b[goal] = 0
    parent_b[goal] = goal
    bk_b: list[deque[int]] = [deque() for _ in range(mod)]
    bk_b[h0 % mod].append(goal)
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
            for nb in pnb[node]:
                c = cost[nb]
                nd = gn + c
                if nd < g_f[nb]:
                    g_f[nb] = nd
                    parent_f[nb] = node
                    nix, niy = nb % w, nb // w
                    h_ni = max(abs(nix - gx), abs(niy - gy)) * CR
                    bk_f[(nd + h_ni) % mod].append(nb)
                    # Check meeting at relaxation
                    if g_b[nb] < INF:
                        cand = nd + g_b[nb]
                        if cand < best:
                            best = cand
                            meet = nb
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
            for nb in pnb[node]:
                nd = gn + c_node
                if nd < g_b[nb]:
                    g_b[nb] = nd
                    parent_b[nb] = node
                    nix, niy = nb % w, nb // w
                    h_ni = max(abs(nix - sx), abs(niy - sy)) * CR
                    bk_b[(nd + h_ni) % mod].append(nb)
                    # Check meeting at relaxation
                    if g_f[nb] < INF:
                        cand = g_f[nb] + nd
                        if cand < best:
                            best = cand
                            meet = nb
        else:
            break

    if meet < 0:
        return None

    # Extract path: start → meet via parent_f, meet → goal via parent_b
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
