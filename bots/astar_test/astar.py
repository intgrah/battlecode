import heapq

from cambc import Controller, EntityType, Environment
from map_belief import _TRANSPORT, COST_IMPASSABLE, COST_ROAD, MapBelief

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


BRIDGE_DELTAS = [
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 2 < dx * dx + dy * dy <= 9
]

EDGES_ROAD = make_edges(WALK_8)
EDGES_CONV = make_edges(WALK_4)
EDGES_FLOW = make_edges(WALK_4, BRIDGE_DELTAS, jump_cost=10)


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


COST_CONV = 3
COST_BRIDGE = 10


def flow_astar(
    belief: MapBelief,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    budget_us: int = 1500,
    ct: Controller | None = None,
) -> list[tuple[int, int]] | None:
    """A* on the resource flow graph. Finds cheapest chain from (sx,sy) to (gx,gy).

    Existing transport buildings with flow < 1.0 cost 0 to reuse.
    Existing transport at capacity costs IMPASSABLE (force reroute).
    Empty buildable tiles cost COST_CONV (cardinal) or COST_BRIDGE (jump).
    Walls, ore, enemy buildings are impassable.
    """
    w, h = belief.w, belief.h
    start_t = ct.get_cpu_time_elapsed() if ct else 0

    if sx == gx and sy == gy:
        return [(sx, sy)]

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
            path: list[tuple[int, int]] = []
            ni = ci
            while ni != -1:
                path.append((ni % w, ni // w))
                ni = parent[ni]
            path.reverse()
            return path

        if f > g[ci] + _heuristic(cx, cy, gx, gy, 1):
            continue

        expanded += 1
        if ct is not None and expanded % 32 == 0:
            if ct.get_cpu_time_elapsed() - start_t > budget_us:
                path = []
                ni = best_ni
                while ni != -1:
                    path.append((ni % w, ni // w))
                    ni = parent[ni]
                path.reverse()
                return path

        for dx, dy, jump in EDGES_FLOW:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            ni = ny * w + nx
            env = belief.env[ni]
            if env is None:
                edge_cost = COST_BRIDGE if jump > 0 else COST_CONV
            elif env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            else:
                ent = belief.entity[ni]
                if ent is None:
                    edge_cost = COST_BRIDGE if jump > 0 else COST_CONV
                else:
                    etype, team = ent
                    if team != belief.my_team:
                        continue
                    if etype in _TRANSPORT or etype == EntityType.CORE:
                        tile_flow = belief.flow(nx, ny)
                        if tile_flow >= 1.0:
                            continue
                        edge_cost = 0
                    else:
                        continue

            new_g = g[ci] + edge_cost
            if new_g >= g[ni]:
                continue
            g[ni] = new_g
            parent[ni] = ci
            hval = _heuristic(nx, ny, gx, gy, 1)
            heapq.heappush(heap, (new_g + hval, hval, ni))
            if hval < best_h:
                best_h = hval
                best_ni = ni

    return None
