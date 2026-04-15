from collections import deque

from bench_nav.common import CE, INF, Path_

assert CE + 2 == 5


def astar_dial_precomp(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    h: list[int],
    start: int,
    goal: int,
) -> Path_:
    """A* (Dial's) from goal to start, using precomputed heuristic."""
    g = [INF] * n
    g[goal] = 0
    h_goal = h[goal]
    if h_goal >= INF:
        return None
    bk = [deque[int]() for _ in range(5)]
    bk[h_goal % 5].append(goal)
    f = h_goal
    emp = 0
    found = False
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
                    found = True
                    break
                for nb in pnb[node]:
                    nd = g_node + cost[nb]
                    if nd < g[nb]:
                        g[nb] = nd
                        bk[(nd + h[nb]) % 5].append(nb)
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
