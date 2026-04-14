import heapq

from bench_nav.common import CR, INF, Path_, extract_parent


def gbfs(w: int, n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
    start_x, start_y = start % w, start // w
    goal_x, goal_y = goal % w, goal // w
    parent = [-1] * n
    parent[start] = start
    h_start = max(abs(start_x - goal_x), abs(start_y - goal_y)) * CR
    q = [(h_start, start)]
    best_h = INF
    best_node = start
    while q:
        h_node, node = heapq.heappop(q)
        if node == goal:
            return extract_parent(parent, start, goal)
        if h_node < best_h:
            best_h = h_node
            best_node = node
        for nb in pnb[node]:
            if parent[nb] != -1:
                continue
            parent[nb] = node
            h_nb = max(abs(nb % w - goal_x), abs(nb // w - goal_y)) * CR
            heapq.heappush(q, (h_nb, nb))
    if best_node == start:
        return None
    return extract_parent(parent, start, best_node)
