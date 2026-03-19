import heapq

from cambc import Controller
from map_belief import COST_IMPASSABLE, COST_ROAD, MapBelief

INF = 1_000_000

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
WALK_4 = [(0, -1), (1, 0), (0, 1), (-1, 0)]


def _heuristic(ax: int, ay: int, bx: int, by: int, min_cost: int) -> int:
    dx = abs(ax - bx)
    dy = abs(ay - by)
    return max(dx, dy) * min_cost + min(dx, dy)


Edge = tuple[int, int, int]


def make_edges(
    walk: list[tuple[int, int]],
    jumps: list[tuple[int, int]] | None = None,
    jump_cost: int = 0,
) -> list[Edge]:
    edges: list[Edge] = [(dx, dy, 0) for dx, dy in walk]
    if jumps is not None:
        edges.extend((dx, dy, jump_cost) for dx, dy in jumps)
    return edges


EDGES_ROAD = make_edges(WALK_8)
EDGES_CONV = make_edges(WALK_4)


def astar(
    belief: MapBelief,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    edges: list[Edge],
    budget_us: int = 1500,
    ct: Controller | None = None,
) -> list[tuple[int, int]] | None:
    w, h = belief.w, belief.h
    start_t = ct.get_cpu_time_elapsed() if ct else 0

    if sx == gx and sy == gy:
        return [(sx, sy)]

    min_cost = COST_ROAD

    g = [INF] * (w * h)
    si = sy * w + sx
    g[si] = 0

    parent = [-1] * (w * h)

    best_h = INF
    best_ni = si

    heap: list[tuple[int, int, int]] = [(0, 0, si)]

    expanded = 0
    while heap:
        f, _, ci = heapq.heappop(heap)
        cx = ci % w
        cy = ci // w

        if cx == gx and cy == gy:
            path = []
            ni = ci
            while ni != -1:
                path.append((ni % w, ni // w))
                ni = parent[ni]
            path.reverse()
            return path

        if f > g[ci] + _heuristic(cx, cy, gx, gy, min_cost):
            continue

        expanded += 1
        if ct is not None and expanded % 32 == 0:
            elapsed = ct.get_cpu_time_elapsed() - start_t
            if elapsed > budget_us:
                path = []
                ni = best_ni
                while ni != -1:
                    path.append((ni % w, ni // w))
                    ni = parent[ni]
                path.reverse()
                return path

        for dx, dy, fixed_cost in edges:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            ni = ny * w + nx
            wt = belief.walkable(nx, ny)
            if wt >= COST_IMPASSABLE:
                continue
            edge_cost = fixed_cost if fixed_cost > 0 else wt
            new_g = g[ci] + edge_cost
            if new_g >= g[ni]:
                continue
            g[ni] = new_g
            parent[ni] = ci
            hval = _heuristic(nx, ny, gx, gy, min_cost)
            heapq.heappush(heap, (new_g + hval, hval, ni))
            if hval < best_h:
                best_h = hval
                best_ni = ni

    return None
