import heapq

from bench_nav.common import INF, Path_, extract_parent


def astar_heap_bfs(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    h_to_goal: list[int],
    start: int,
    goal: int,
) -> Path_:
    """A* heap with precomputed BFS-hops heuristic toward goal.

    h_to_goal[node] = hop count from node to goal (ignoring tile costs).
    Admissible when CR=1 (road cost 1).
    """
    g = [INF] * n
    g[start] = 0
    parent = [-1] * n
    parent[start] = start
    h_start = h_to_goal[start]
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
                h_nb = h_to_goal[nb]
                heapq.heappush(q, (nd + h_nb, h_nb, nb))
    return None
