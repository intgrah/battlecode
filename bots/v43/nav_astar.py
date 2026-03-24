from typing import TYPE_CHECKING

from astar import Astar
from map_belief import COST_EMPTY, COST_IMPASSABLE, MapBelief

if TYPE_CHECKING:
    from cambc import Controller

WALK_8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def _build_nav_edges(belief: MapBelief) -> list[list[tuple[int, int]]]:
    w, h = belief.w, belief.h
    n = w * h
    edges: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for ci in range(n):
        cx, cy = ci % w, ci // w
        result = edges[ci]
        for dx, dy in WALK_8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                wt = belief.walkable(nx, ny)
                if wt < COST_IMPASSABLE:
                    result.append((ni, wt))
    return edges


def _build_nav_heuristic(w: int, h: int, gx: int, gy: int) -> list[int]:
    n = w * h
    table = [0] * n
    for i in range(n):
        x, y = i % w, i // w
        dx = abs(x - gx)
        dy = abs(y - gy)
        table[i] = max(dx, dy) * COST_EMPTY
    return table


def nav_astar(
    belief: MapBelief,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    ct: "Controller",
    budget_us: int = 1800,
) -> list[tuple[int, int]] | None:
    w, h = belief.w, belief.h
    gi = gy * w + gx
    edges = _build_nav_edges(belief)
    h_table = _build_nav_heuristic(w, h, gx, gy)
    search = Astar(w, h, sx, sy, {gi}, edges, h_table)
    search.compute(ct, budget_us)
    return search.get_path()
