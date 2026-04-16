from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Controller, Position
from util import INF

if TYPE_CHECKING:
    from builder import Builder


class AStarSearch:
    TARGET_DRIFT_SQ: Final = 25
    CPU_BUDGET: Final = 1729
    DIAG_WEIGHT: Final = 4
    BRIDGE_DELTAS: Final = tuple(
        (dx, dy, 7)
        for dx in range(-3, 4)
        for dy in range(-3, 4)
        if 3 <= dx * dx + dy * dy <= 9
    )
    CONV_NEIGHBORS: Final = (
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (1, 1, DIAG_WEIGHT),
        (1, -1, DIAG_WEIGHT),
        (-1, 1, DIAG_WEIGHT),
        (-1, -1, DIAG_WEIGHT),
        *BRIDGE_DELTAS,
    )

    def __init__(self, builder: Builder) -> None:
        self.builder = builder
        w, h = builder.w, builder.h
        n = w * h
        self._w = w
        self._h = h
        self._neighbors: Final[list[list[tuple[int, int]]]] = [
            [
                (ny * w + nx, extra)
                for dx, dy, extra in AStarSearch.CONV_NEIGHBORS
                if 0 <= (nx := cx + dx) < w and 0 <= (ny := cy + dy) < h
            ]
            for cy in range(h)
            for cx in range(w)
        ]
        self._dist: list[int] = [INF] * n
        self._dist_reset: Final[tuple[int, ...]] = (INF,) * n
        self._finished = True
        self._target: Position | None = None

    def search(
        self,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        w = self._w
        si = start.y * w + start.x
        gi = target.y * w + target.x

        if (
            self._finished
            or self._target is None
            or target.distance_squared(self._target) > AStarSearch.TARGET_DRIFT_SQ
        ):
            self._dist[:] = self._dist_reset
        else:
            target = self._target
            gi = target.y * w + target.x

        self._target = target

        b = self.builder
        cost = b.conveyor_cost_grid
        dist = self._dist
        neighbors = self._neighbors
        sx = start.x
        sy = start.y

        if dist[gi] is INF:
            dist[gi] = 0

        nb_count = 24
        gx, gy = target.x, target.y
        f0 = abs(gx - sx) + abs(gy - sy)
        bk: list[list[int]] = [[] for _ in range(nb_count)]
        bk[f0 % nb_count].append(gi)
        cur_f = f0
        emp = 0

        found = False
        while emp < nb_count:
            bucket = bk[cur_f % nb_count]
            if not bucket:
                cur_f += 1
                emp += 1
                continue
            emp = 0
            for node_i in bucket:
                ny_, nx_ = divmod(node_i, w)
                node_h = abs(nx_ - sx) + abs(ny_ - sy)
                if dist[node_i] + node_h != cur_f:
                    continue
                if node_i == si:
                    found = True
                    break
                if ct.get_cpu_time_elapsed() > AStarSearch.CPU_BUDGET:
                    self._finished = False
                    return None
                gn = dist[node_i]
                for ni, extra in neighbors[node_i]:
                    mc = cost[ni]
                    if mc >= INF:
                        continue
                    nd = gn + mc + extra
                    if nd >= dist[ni]:
                        continue
                    dist[ni] = nd
                    ny2, nx2 = divmod(ni, w)
                    h_val = abs(nx2 - sx) + abs(ny2 - sy)
                    bk[(nd + h_val) % nb_count].append(ni)
            if found:
                break
            bk[cur_f % nb_count] = []
            cur_f += 1

        self._finished = True
        if not found:
            return None

        path: list[int] = [si]
        node = si
        while node != gi:
            best_dist = INF
            best = node
            for ni, extra in neighbors[node]:
                d = dist[ni]
                if d is INF or cost[ni] >= INF:
                    continue
                d += extra
                if d < best_dist:
                    best_dist = d
                    best = ni
            if best == node:
                return None
            path.append(best)
            node = best

        return [Position(i % w, i // w) for i in path]

    def search_blocked(
        self,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        b = self.builder
        cost = b.conveyor_cost_grid
        w = b.w
        saved: list[tuple[int, int]] = []
        for pos in b.nearby_tiles:
            if pos in b.all_bots and pos != start:
                idx = pos.y * w + pos.x
                saved.append((idx, cost[idx]))
                cost[idx] = INF
        result = self.search(ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result
