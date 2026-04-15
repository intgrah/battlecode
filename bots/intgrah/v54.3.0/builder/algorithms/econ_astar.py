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
        self._pw = builder.pad_w
        self._pad = builder.pad
        pn = builder.pad_w * builder.pad_h
        self._flat_neighbors: Final[list[tuple[int, int]]] = [
            (dy * self._pw + dx, extra) for dx, dy, extra in AStarSearch.CONV_NEIGHBORS
        ]
        self._dist: list[int] = [INF] * pn
        self._dist_reset: Final[tuple[int, ...]] = (INF,) * pn
        self._finished = True
        self._target: Position | None = None

    def search(
        self,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        if (
            self._finished
            or self._target is None
            or target.distance_squared(self._target) > AStarSearch.TARGET_DRIFT_SQ
        ):
            self._dist[:] = self._dist_reset
        else:
            target = self._target

        self._target = target

        b = self.builder
        cost = b.conveyor_cost_grid
        pw = self._pw
        pad = self._pad
        dist = self._dist
        flat_neighbors = self._flat_neighbors
        sx_p = start.x + pad
        sy_p = start.y + pad
        gx_p = target.x + pad
        gy_p = target.y + pad

        gi = gy_p * pw + gx_p
        si = sy_p * pw + sx_p
        if dist[gi] is INF:
            dist[gi] = 0

        nb_count = 24
        f0 = abs(gx_p - sx_p) + abs(gy_p - sy_p)
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
                ny_, nx_ = divmod(node_i, pw)
                node_h = abs(nx_ - sx_p) + abs(ny_ - sy_p)
                if dist[node_i] + node_h != cur_f:
                    continue
                if node_i == si:
                    found = True
                    break
                if ct.get_cpu_time_elapsed() > AStarSearch.CPU_BUDGET:
                    self._finished = False
                    return None
                gn = dist[node_i]
                for off, extra in flat_neighbors:
                    ni = node_i + off
                    mc = cost[ni]
                    if mc >= INF:
                        continue
                    nd = gn + mc + extra
                    if nd >= dist[ni]:
                        continue
                    dist[ni] = nd
                    ny2, nx2 = divmod(ni, pw)
                    h_val = abs(nx2 - sx_p) + abs(ny2 - sy_p)
                    bk[(nd + h_val) % nb_count].append(ni)
            if found:
                break
            bk[cur_f % nb_count] = []
            cur_f += 1

        self._finished = True
        if not found:
            return None

        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = INF
            best = current
            ci = (current.y + pad) * pw + (current.x + pad)
            for off, extra in flat_neighbors:
                idx = ci + off
                d = dist[idx]
                if d is INF or cost[idx] >= INF:
                    continue
                d += extra
                if d < best_dist:
                    best_dist = d
                    y_p, x_p = divmod(idx, pw)
                    best = Position(x_p - pad, y_p - pad)
            current = best
        path.append(target)
        return path

    def search_blocked(
        self,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        b = self.builder
        cost = b.conveyor_cost_grid
        saved: list[tuple[int, int]] = []
        for pos in b.nearby_tiles:
            if pos in b.all_bots and pos != start:
                idx = b._pidx(pos)
                saved.append((idx, cost[idx]))
                cost[idx] = INF
        result = self.search(ct, start, goal)
        for idx, val in saved:
            cost[idx] = val
        return result
