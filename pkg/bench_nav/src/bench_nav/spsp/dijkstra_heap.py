import heapq

from bench_nav.common import INF, Path_, extract_parent


def dijkstra_heap(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> Path_:
    dist = [INF] * n
    dist[start] = 0
    parent = [-1] * n
    parent[start] = start
    q = [(0, start)]
    while q:
        d, node = heapq.heappop(q)
        if node == goal:
            return extract_parent(parent, start, goal)
        if d > dist[node]:
            continue
        g_node = dist[node]
        for nb in pnb[node]:
            c = cost[nb]
            nd = g_node + c
            if nd < dist[nb]:
                dist[nb] = nd
                parent[nb] = node
                heapq.heappush(q, (nd, nb))
    return None
