from collections import deque

from bench_nav.common import CE, INF, Path_, extract_parent

assert CE + 2 == 5


def astar_dial_precomp(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    h: list[int],
    start: int,
    goal: int,
) -> Path_:
    """A* (Dial's) backward from goal to start, using precomputed heuristic (distance from start)."""
    g = [INF] * n
    g[goal] = 0
    parent = [-1] * n
    parent[goal] = goal
    h_goal = h[goal]
    if h_goal >= INF:
        return None
    bk = [deque[int]() for _ in range(5)]
    bk[h_goal % 5].append(goal)
    f = h_goal
    emp = 0
    while emp < 5:
        bki = bk[f % 5]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                g_node = g[node]
                if g_node + h[node] != f:
                    continue
                if node == start:
                    path = extract_parent(parent, goal, start)
                    if path is not None:
                        path.reverse()
                    return path
                for nb in pnb[node]:
                    nd = g_node + cost[nb]
                    if nd < g[nb]:
                        g[nb] = nd
                        parent[nb] = node
                        bk[(nd + h[nb]) % 5].append(nb)
        else:
            emp += 1
        f += 1
    return None
