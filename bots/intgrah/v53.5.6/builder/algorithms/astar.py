from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from builder.algorithms.bfs import extract_path
from cambc import Controller, Position
from util import INF, ROAD_COST

if TYPE_CHECKING:
    from builder.state import State

ASTAR_BUDGET_MICROSECONDS = 1729


def _astar(
    pnb: list[list[int]],
    cost: list[int],
    nav_dist: list[int],
    w: int,
    ct: Controller,
    start: Position,
    goal: Position,
) -> Position | None:
    si = start.y * w + start.x
    gi = goal.y * w + goal.x
    if si == gi:
        return start

    n = len(cost)
    dist = [INF] * n

    dist[gi] = 0
    h_gi = nav_dist[gi] * 2

    mod = ROAD_COST + 2
    bk: list[deque[int]] = [deque() for _ in range(mod)]
    bk[h_gi % mod].append(gi)
    cur_f = h_gi
    emp = 0

    while emp < mod:
        bi = cur_f % mod
        if not bk[bi]:
            cur_f += 1
            emp += 1
            continue
        emp = 0
        node_i = bk[bi].popleft()
        if dist[node_i] + nav_dist[node_i] * 2 != cur_f:
            continue
        if node_i == si:
            best_d = INF
            best_ni = si
            for ni in pnb[si]:
                if cost[ni] >= INF:
                    continue
                d = dist[ni]
                if d < best_d:
                    best_d = d
                    best_ni = ni
            if best_ni == si:
                return start
            return Position(best_ni % w, best_ni // w)
        if ct.get_cpu_time_elapsed() > ASTAR_BUDGET_MICROSECONDS:
            return None
        gn = dist[node_i]
        for ni in pnb[node_i]:
            nd = gn + cost[ni]
            if nd < dist[ni]:
                dist[ni] = nd
                bk[(nd + nav_dist[ni] * 2) % mod].append(ni)
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
    result = _astar(state.pnb, cost, state.bfs_dist, state.w, ct, start, goal)
    t1 = ct.get_cpu_time_elapsed()

    for idx, val in saved:
        cost[idx] = val

    if result is not None:
        print(f"    move_astar={t1 - t0}us")
        ct.draw_indicator_dot(goal, 255, 255, 255)
        return result

    path = extract_path(state, start.x, start.y, goal.x, goal.y)
    t2 = ct.get_cpu_time_elapsed()
    gi = goal.y * state.w + goal.x
    print(
        f"    move_astar={t1 - t0}us bfs_extract={t2 - t1}us bfs_goal={state.bfs_dist[gi]} path_len={len(path) if path else 0}"
    )
    if path and len(path) > 1:
        _draw_path(ct, path)
        return path[1]
    return None
