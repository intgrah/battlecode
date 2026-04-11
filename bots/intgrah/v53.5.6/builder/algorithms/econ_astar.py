from __future__ import annotations

import heapq
import random
from typing import TYPE_CHECKING

from cambc import Controller, Position
from util import INF

if TYPE_CHECKING:
    from builder.state import State

_CPU_BUDGET = 1729
_TIEBREAK_EPS = 1e-5

DIAG_WEIGHT = 4
COST_BRIDGE_EXTRA = 7
_BRIDGE_DELTAS = [
    (dx, dy)
    for dx in range(-3, 4)
    for dy in range(-3, 4)
    if 3 <= dx * dx + dy * dy <= 9
]
_CONV_NEIGHBORS = [
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (1, 1, DIAG_WEIGHT),
    (1, -1, DIAG_WEIGHT),
    (-1, 1, DIAG_WEIGHT),
    (-1, -1, DIAG_WEIGHT),
] + [(dx, dy, COST_BRIDGE_EXTRA) for dx, dy in _BRIDGE_DELTAS]
random.shuffle(_CONV_NEIGHBORS)

_no_path: bool = False


def conv_pathfind(
    state: State, ct: Controller, start: Position, target: Position
) -> list[Position] | None:
    t0 = ct.get_cpu_time_elapsed()
    result = _conv_astar(state, ct, start, target)
    t1 = ct.get_cpu_time_elapsed()
    print(f"    conv_astar={t1 - t0}us")
    return result


def conv_unreachable(_target: Position) -> bool:
    return _no_path


def _conv_astar(
    state: State,
    ct: Controller,
    start: Position,
    goal: Position,
) -> list[Position] | None:
    global _no_path  # noqa: PLW0603
    _no_path = False

    cost = state.conveyor_cost_grid
    w = state.w
    h_map = state.h
    n = w * h_map

    dist = [INF] * n
    visited = bytearray((n + 7) // 8)

    gi = goal.y * w + goal.x
    si = start.y * w + start.x
    dist[gi] = 0
    visited[gi // 8] |= 1 << (gi % 8)

    q: list[tuple[float, int]] = []
    heapq.heappush(q, (0.0, gi))

    while q:
        _, ci = heapq.heappop(q)
        if ci == si:
            path: list[Position] = [start]
            cur = si
            while cur != gi:
                best_d: float = INF
                best_ni = cur
                cx, cy = cur % w, cur // w
                for dx, dy, extra in _CONV_NEIGHBORS:
                    nx, ny = cx + dx, cy + dy
                    if not (0 <= nx < w and 0 <= ny < h_map):
                        continue
                    ni = ny * w + nx
                    if not (visited[ni // 8] & (1 << (ni % 8))):
                        continue
                    if cost[ni] >= INF:
                        continue
                    d = dist[ni] + extra
                    if d < best_d:
                        best_d = d
                        best_ni = ni
                if best_ni == cur:
                    break
                cur = best_ni
                path.append(Position(cur % w, cur // w))
            return path

        if ct.get_cpu_time_elapsed() > _CPU_BUDGET:
            return None

        gn = dist[ci]
        cx, cy = ci % w, ci // w
        for dx, dy, extra in _CONV_NEIGHBORS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h_map):
                continue
            ni = ny * w + nx
            seen = visited[ni // 8] & (1 << (ni % 8))
            if not seen:
                dist[ni] = INF
            visited[ni // 8] |= 1 << (ni % 8)
            mc = cost[ni]
            if mc >= INF:
                continue
            nd = gn + mc + extra
            if nd >= dist[ni]:
                continue
            dist[ni] = nd
            dx_h = abs(nx - start.x)
            dy_h = abs(ny - start.y)
            f = nd + (dx_h + dy_h) + _TIEBREAK_EPS * (dx_h + dy_h)
            heapq.heappush(q, (f, ni))

    _no_path = True
    return None
