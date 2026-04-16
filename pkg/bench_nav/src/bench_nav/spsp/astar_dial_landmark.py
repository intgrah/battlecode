from collections import deque

from bench_nav.common import CE, INF, Path_, extract_parent

assert CE + 2 == 5


def astar_dial_landmark(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    landmark_dists: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    """A* (Dial's) backward from goal to start, using landmark heuristic."""
    k = len(landmark_dists)
    start_ld = [landmark_dists[j][start] for j in range(k)]
    g = [INF] * n
    g[goal] = 0
    parent = [-1] * n
    parent[goal] = goal
    h_goal = max(abs(landmark_dists[j][goal] - start_ld[j]) for j in range(k))
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
                h_node = max(
                    abs(landmark_dists[j][node] - start_ld[j]) for j in range(k)
                )
                if g_node + h_node != f:
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
                        h_nb = max(
                            abs(landmark_dists[j][nb] - start_ld[j]) for j in range(k)
                        )
                        bk[(nd + h_nb) % 5].append(nb)
        else:
            emp += 1
        f += 1
    return None


def astar_dial_landmark_cheb(
    w: int,
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    landmark_dists: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    """A* (Dial's) backward from goal to start, using max(landmark, chebyshev from start)."""
    k = len(landmark_dists)
    start_x, start_y = start % w, start // w
    start_ld = [landmark_dists[j][start] for j in range(k)]
    g = [INF] * n
    g[goal] = 0
    parent = [-1] * n
    parent[goal] = goal
    h_goal = max(  # noqa: PLW3301
        max(abs(goal % w - start_x), abs(goal // w - start_y)),
        max(abs(landmark_dists[j][goal] - start_ld[j]) for j in range(k)),
    )
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
                h_node = max(  # noqa: PLW3301
                    max(abs(node % w - start_x), abs(node // w - start_y)),
                    max(abs(landmark_dists[j][node] - start_ld[j]) for j in range(k)),
                )
                if g_node + h_node != f:
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
                        h_nb = max(  # noqa: PLW3301
                            max(abs(nb % w - start_x), abs(nb // w - start_y)),
                            max(
                                abs(landmark_dists[j][nb] - start_ld[j])
                                for j in range(k)
                            ),
                        )
                        bk[(nd + h_nb) % 5].append(nb)
        else:
            emp += 1
        f += 1
    return None
