from collections import deque

from bench_nav.common import CE, INF, Path_


def astar_dial_bfs(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    bfs_h: list[int],
    start: int,
    goal: int,
) -> Path_:
    """A* (Dial's) from goal to start, using precomputed BFS heuristic."""
    mod = CE + 2
    g = [INF] * n
    g[goal] = 0
    h_goal = bfs_h[goal]
    if h_goal >= INF:
        return None
    bk = [deque[int]() for _ in range(mod)]
    bk[h_goal % mod].append(goal)
    f = h_goal
    emp = 0
    found = False
    while emp < mod:
        bki = bk[f % mod]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                g_node = g[node]
                if g_node + bfs_h[node] != f:
                    continue
                if node == start:
                    found = True
                    break
                for nb in pnb[node]:
                    nd = g_node + cost[nb]
                    if nd < g[nb]:
                        g[nb] = nd
                        bk[(nd + bfs_h[nb]) % mod].append(nb)
            if found:
                break
        else:
            emp += 1
        f += 1
    if not found:
        return None
    path = [start]
    cur = start
    while cur != goal:
        d = g[cur]
        for nb in pnb[cur]:
            if g[nb] + cost[cur] == d:
                path.append(nb)
                cur = nb
                break
        else:
            return None
    return path
