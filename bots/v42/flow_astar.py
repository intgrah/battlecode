from astar import INF, Astar
from cambc import EntityType, Environment
from map_belief import _TRANSPORT, MapBelief

WALK_4 = [(0, -1), (1, 0), (0, 1), (-1, 0)]

BRIDGE_DELTAS = [
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 2 < dx * dx + dy * dy <= 9
]

COST_REUSE = 0
COST_CONV = 3
COST_BRIDGE = 10
COST_ROAD_REPLACE = 3
CONV_CUTOFF_SQ = 0

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)

TI = 1
AX = 2
RAX = 4


def _build_leakage_mask(belief: MapBelief) -> list[int]:
    w, h = belief.w, belief.h
    n = w * h
    mask = [0] * n
    for i in range(n):
        ent = belief.entity[i]
        if ent is None:
            continue
        etype, team = ent
        if team != belief.my_team:
            continue
        if etype == EntityType.FOUNDRY:
            ix, iy = i % w, i // w
            for ddx, ddy in WALK_4:
                nx, ny = ix + ddx, iy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    mask[ny * w + nx] |= RAX
        elif etype == EntityType.SPLITTER:
            d = belief.direction[i]
            if d is None:
                continue
            ix, iy = i % w, i // w
            dx, dy = d.delta()
            commodity = 0
            f = belief.my_flow
            if f.ti[i] > 0:
                commodity |= TI
            if f.ax[i] > 0:
                commodity |= AX
            if f.rax[i] > 0:
                commodity |= RAX
            if commodity == 0:
                continue
            for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                nx, ny = ix + odx, iy + ody
                if 0 <= nx < w and 0 <= ny < h:
                    mask[ny * w + nx] |= commodity

    for i in range(n):
        e = belief.env[i]
        if e == Environment.ORE_TITANIUM:
            commodity = TI
        elif e == Environment.ORE_AXIONITE:
            commodity = AX
        else:
            continue
        ix, iy = i % w, i // w
        for ddx, ddy in WALK_4:
            nx, ny = ix + ddx, iy + ddy
            if 0 <= nx < w and 0 <= ny < h:
                mask[ny * w + nx] |= commodity

    return mask


def _build_flow_edges(
    belief: MapBelief,
    leakage_mask: list[int],
    banned_leakage: int,
    goal_set: set[int] | None = None,
) -> list[list[tuple[int, int]]]:
    w, h = belief.w, belief.h
    n = w * h
    blocked = belief.my_flow.blocked
    env = belief.env
    if goal_set is None:
        goal_set = set()
    entity = belief.entity
    direction = belief.direction
    bridge_target = belief.bridge_target
    core_x, core_y = belief.my_core

    edges: list[list[tuple[int, int]]] = [[] for _ in range(n)]

    for ci in range(n):
        if blocked[ci]:
            continue
        e = env[ci]
        if e is not None and e in _IMPASSABLE_ENV:
            continue
        ent = entity[ci]
        if ent is not None and ent[1] != belief.my_team:
            continue

        cx, cy = ci % w, ci // w

        def passable(ni: int) -> bool:
            if blocked[ni]:
                return False
            ne = env[ni]
            return ne is None or ne not in _IMPASSABLE_ENV

        def no_leak(ni: int) -> bool:
            return leakage_mask[ni] & banned_leakage == 0

        result = edges[ci]

        if ent is not None and ent[0] != EntityType.MARKER:
            etype = ent[0]

            if etype == EntityType.CORE:
                for ddx, ddy in WALK_4:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if passable(ni):
                            result.append((ni, 0))

            elif etype in _TRANSPORT:
                d = direction[ci]
                bt = bridge_target[ci]
                if etype == EntityType.BRIDGE and bt is not None:
                    bx, by = bt
                    if 0 <= bx < w and 0 <= by < h:
                        ni = by * w + bx
                        if passable(ni):
                            result.append((ni, COST_REUSE))
                elif d is not None:
                    ddx, ddy = d.delta()
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if passable(ni):
                            result.append((ni, COST_REUSE))

            elif etype == EntityType.ROAD:
                core_dist_sq = (cx - core_x) ** 2 + (cy - core_y) ** 2
                if core_dist_sq > CONV_CUTOFF_SQ:
                    for ddx, ddy in WALK_4:
                        nx, ny = cx + ddx, cy + ddy
                        if 0 <= nx < w and 0 <= ny < h:
                            ni = ny * w + nx
                            if passable(ni) and no_leak(ni):
                                result.append((ni, COST_ROAD_REPLACE))
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if passable(ni) and no_leak(ni):
                            result.append((ni, COST_BRIDGE))

        else:
            core_dist_sq = (cx - core_x) ** 2 + (cy - core_y) ** 2
            if core_dist_sq > CONV_CUTOFF_SQ:
                for ddx, ddy in WALK_4:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if passable(ni) and no_leak(ni):
                            result.append((ni, COST_CONV))
            for ddx, ddy in BRIDGE_DELTAS:
                nx, ny = cx + ddx, cy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if passable(ni) and no_leak(ni):
                        result.append((ni, COST_BRIDGE))

    return edges


def _build_heuristic(w: int, h: int, gx: int, gy: int) -> list[int]:
    n = w * h
    table = [0] * n
    for i in range(n):
        x, y = i % w, i // w
        table[i] = abs(x - gx) + abs(y - gy)
    return table


def flow_astar(
    belief: MapBelief,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    goal_set: set[int] | None = None,
    banned_leakage: int = 0,
) -> Astar:
    w, h = belief.w, belief.h
    if goal_set is None:
        goal_set = set()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cx, cy = gx + dx, gy + dy
                if 0 <= cx < w and 0 <= cy < h:
                    goal_set.add(cy * w + cx)
    leakage_mask = _build_leakage_mask(belief)
    edges = _build_flow_edges(belief, leakage_mask, banned_leakage, goal_set)
    h_table = _build_heuristic(w, h, gx, gy)
    return Astar(w, h, sx, sy, goal_set, edges, h_table)
