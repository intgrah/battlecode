import heapq
import sys

from bench_nav.common import INF


def dijkstra_full(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    """Reference implementation to compare ground truth"""
    dist: list[int] = [INF] * n
    dist[start] = 0
    heap: list[tuple[int, int]] = [(0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for nb in pnb[node]:
            c = cost[nb]
            nd = d + c
            if nd < dist[nb]:
                dist[nb] = nd
                heapq.heappush(heap, (nd, nb))
    return dist


def optimal_first_moves(
    n: int,
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
    dist: list[int],
) -> set[int]:
    if start == goal:
        return {start}
    if dist[goal] >= INF:
        return set()
    on_shortest: list[bool] = [False] * n
    on_shortest[goal] = True
    q = [goal]
    append = q.append
    for node in q:
        for nb in pnb[node]:
            if on_shortest[nb]:
                continue
            c = cost[node]
            if dist[nb] + c == dist[node]:
                on_shortest[nb] = True
                append(nb)
    moves: set[int] = set()
    for nb in pnb[start]:
        if not on_shortest[nb]:
            continue
        c = cost[nb]
        if dist[start] + c == dist[nb]:
            moves.add(nb)
    return moves


def path_cost(w: int, cost: list[int], path: list[int]) -> int:
    if len(path) < 2:
        return 0
    total = 0
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        ax, ay = a % w, a // w
        bx, by = b % w, b // w
        dx, dy = abs(bx - ax), abs(by - ay)
        if dx > 1 or dy > 1:
            return INF
        c = cost[b]
        if c >= INF:
            return INF
        total += c
    return total


def validate_path(
    w: int,
    n: int,
    cost: list[int],
    name: str,
    path: list[int],
    start: int,
    algo_name: str,
) -> bool:
    if not path:
        return True
    if path[0] != start:
        print(
            f"INVALID {algo_name} on {name}: start={path[0]} expected={start}",
            file=sys.stderr,
        )
        return False
    for k, node in enumerate(path):
        if node < 0 or node >= n:
            print(
                f"INVALID {algo_name} on {name}: node {k} out of bounds: {node}",
                file=sys.stderr,
            )
            return False
        if k > 0 and cost[node] >= INF:
            print(
                f"INVALID {algo_name} on {name}: node {k} impassable: {node}",
                file=sys.stderr,
            )
            return False
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        dx = abs(a % w - b % w)
        dy = abs(a // w - b // w)
        if dx > 1 or dy > 1:
            print(
                f"INVALID {algo_name} on {name}: non-adjacent step {k}: "
                f"({a % w},{a // w})->({b % w},{b // w})",
                file=sys.stderr,
            )
            return False
    return True


def extract_path_from_dist(
    dist: list[int],
    cost: list[int],
    pnb: list[list[int]],
    start: int,
    goal: int,
) -> list[int] | None:
    if dist[goal] >= INF:
        return None
    path = [goal]
    cur = goal
    while cur != start:
        d = dist[cur]
        for nb in pnb[cur]:
            if dist[nb] + cost[cur] == d:
                path.append(nb)
                cur = nb
                break
        else:
            return None
    path.reverse()
    return path


def reference_dist(
    n: int, cost: list[int], pnb: list[list[int]], start: int
) -> list[int]:
    dist: list[int] = [INF] * n
    dist[start] = 0
    heap: list[tuple[int, int]] = [(0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        for nb in pnb[node]:
            nd = d + cost[nb]
            if nd < dist[nb]:
                dist[nb] = nd
                heapq.heappush(heap, (nd, nb))
    return dist


def parent_to_dist(parent: list[int], cost: list[int], n: int, start: int) -> list[int]:
    children: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        p = parent[i]
        if p not in (-1, i):
            children[p].append(i)
    dist: list[int] = [INF] * n
    dist[start] = 0
    q = [start]
    append = q.append
    for node in q:
        for child in children[node]:
            dist[child] = dist[node] + cost[child]
            append(child)
    return dist


def expanded_parent_to_dist(
    parent: list[int],
    n: int,
    start: int,
) -> list[int]:
    total = len(parent)
    children: list[list[int]] = [[] for _ in range(total)]
    for i in range(total):
        p = parent[i]
        if p not in (-1, i):
            children[p].append(i)
    full_dist: list[int] = [INF] * total
    full_dist[start] = 0
    q = [start]
    append = q.append
    for node in q:
        for child in children[node]:
            full_dist[child] = full_dist[node] + 1
            append(child)
    dist: list[int] = [INF] * n
    dist[start] = 0
    for i in range(n):
        if full_dist[i] is not INF:
            dist[i] = full_dist[i]
    return dist
