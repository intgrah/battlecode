from __future__ import annotations

import random
from typing import TYPE_CHECKING

from builder.algorithms.bfs import extract_path
from cambc import Controller, Position
from config import DEBUG_DUMP
from util import DIR8_DELTA, INF

if TYPE_CHECKING:
    from builder.state import State

ASTAR_BUDGET_MICROSECONDS = 1729

_DIR8_DELTA = DIR8_DELTA.copy()
random.shuffle(_DIR8_DELTA)
_MOVE_NEIGHBORS = [(dx, dy, 0) for dx, dy in _DIR8_DELTA]


def _move_astar(
    cost: list[int],
    nav_dist: list[int],
    w: int,
    h: int,
    ct: Controller,
    start: Position,
    goal: Position,
) -> Position | None:
    si = start.y * w + start.x
    gi = goal.y * w + goal.x
    if si == gi:
        return start

    n = w * h
    dist = [INF] * n
    visited = bytearray((n + 7) // 8)

    dist[gi] = 0
    visited[gi // 8] |= 1 << (gi % 8)

    def heuristic(ni: int) -> int:
        d = nav_dist[ni]
        if d == -1:
            nx, ny = ni % w, ni // w
            dx = abs(nx - start.x)
            dy = abs(ny - start.y)
            return max(dx, dy) * 2
        return d * 2

    nb_count = 10
    f0 = heuristic(gi)
    bk: list[list[int]] = [[] for _ in range(nb_count)]
    bk[f0 % nb_count].append(gi)
    cur_f = f0
    emp = 0

    while emp < nb_count:
        bucket = bk[cur_f % nb_count]
        if not bucket:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        for node_i in bucket:
            if dist[node_i] + heuristic(node_i) != cur_f:
                continue
            if node_i == si:
                best_d = INF
                best_pos = start
                for dx, dy, extra in _MOVE_NEIGHBORS:
                    nx, ny = start.x + dx, start.y + dy
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    ni = ny * w + nx
                    if not (visited[ni // 8] & (1 << (ni % 8))):
                        continue
                    if cost[ni] >= INF:
                        continue
                    d = dist[ni] + extra
                    if d < best_d:
                        best_d = d
                        best_pos = Position(nx, ny)
                return best_pos
            if ct.get_cpu_time_elapsed() > ASTAR_BUDGET_MICROSECONDS:
                return None
            gn = dist[node_i]
            for dx, dy, extra in _MOVE_NEIGHBORS:
                nx, ny = node_i % w + dx, node_i // w + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                ni = ny * w + nx
                if visited[ni // 8] & (1 << (ni % 8)):
                    continue
                visited[ni // 8] |= 1 << (ni % 8)
                mc = cost[ni]
                if mc >= INF:
                    continue
                nd = gn + mc + extra
                dist[ni] = nd
                f = nd + heuristic(ni)
                bk[f % nb_count].append(ni)
        bk[cur_f % nb_count] = []
        cur_f += 1

    return None


def _draw_path(ct: Controller, path: list[Position]) -> None:
    for i in range(len(path) - 1):
        ct.draw_indicator_line(path[i], path[i + 1], 255, 255, 255)


def pathfind_move(
    state: State, ct: Controller, start: Position, goal: Position
) -> Position | None:
    cost = state.nav_cost
    saved: list[tuple[int, int]] = []
    for pos in ct.get_nearby_tiles(2):
        if ct.get_tile_builder_bot_id(pos) is not None and pos != start:
            idx = pos.y * state.w + pos.x
            saved.append((idx, cost[idx]))
            cost[idx] = INF

    t0 = ct.get_cpu_time_elapsed()
    result = _move_astar(cost, state.bfs_dist, state.w, state.h, ct, start, goal)
    t1 = ct.get_cpu_time_elapsed()

    for idx, val in saved:
        cost[idx] = val

    if result is not None:
        print(f"    move_astar={t1 - t0}us")
        if DEBUG_DUMP:
            ct.draw_indicator_dot(goal, 255, 255, 255)
        return result

    path = extract_path(state, start.x, start.y, goal.x, goal.y)
    t2 = ct.get_cpu_time_elapsed()
    print(f"    move_astar={t1 - t0}us bfs_extract={t2 - t1}us")
    if path and len(path) > 1:
        if DEBUG_DUMP:
            _draw_path(ct, path)
        return path[1]
    return None
