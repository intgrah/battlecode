import heapq

from bench_nav.common import CR, INF, Path_, extract_parent

assert CR == 1


def astar_heap_cheb(
    w: int,
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    start_x, start_y = start % w, start // w
    goal_x, goal_y = goal % w, goal // w
    g = [INF] * n
    g[start] = 0
    parent = [-1] * n
    parent[start] = start
    h_start = max(abs(start_x - goal_x), abs(start_y - goal_y))
    q = [(h_start, h_start, start)]
    while q:
        f, h_node, node = heapq.heappop(q)
        if f > g[node] + h_node:
            continue
        if node == goal:
            return extract_parent(parent, start, goal)
        g_node = g[node]
        for nb in pnb[node]:
            nd = g_node + cost[nb]
            if nd < g[nb]:
                g[nb] = nd
                parent[nb] = node
                h_nb = max(abs(nb % w - goal_x), abs(nb // w - goal_y))
                heapq.heappush(q, (nd + h_nb, h_nb, nb))
    return None
