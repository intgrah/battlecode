from __future__ import annotations

import heapq
from typing import TYPE_CHECKING, Final

from cambc import Controller, Position
from util import DIR8_DELTA, INF

if TYPE_CHECKING:
    from builder import Builder


class MoveHeapAstar:
    CPU_BUDGET: Final = 1729
    TARGET_DRIFT_SQ: Final = 25

    def __init__(self, builder: Builder) -> None:
        self.builder = builder
        w, h = builder.w, builder.h
        self.w = w
        self.h = h
        self.pad_w = builder.pad_w
        self.pad = builder.pad
        pn = builder.pad_w * builder.pad_h
        self.dir8_delta: Final = DIR8_DELTA.copy()
        builder.rng.shuffle(self.dir8_delta)
        self.dist: list[int] = [INF] * pn
        self.dist_reset: Final[tuple[int, ...]] = (INF,) * pn
        self.q: list[tuple[float, int, Position]] = []
        self.finished = True
        self.target: Position | None = None

    def search(
        self,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        if (
            self.finished
            or self.target is None
            or target.distance_squared(self.target) > MoveHeapAstar.TARGET_DRIFT_SQ
        ):
            self.dist[:] = self.dist_reset
            self.q.clear()
        else:
            target = self.target

        self.target = target

        b = self.builder
        cost = b.cost_grid
        bfs_dist = b.bfs_dist
        w = self.w
        h = self.h
        pad = self.pad
        pad_w = self.pad_w
        dist = self.dist
        dir8_delta = self.dir8_delta
        q = self.q

        gi = (target.y + pad) * pad_w + (target.x + pad)
        if dist[gi] is INF:
            dist[gi] = 0
            heapq.heappush(q, (0, 0, target))

        sx, sy = start.x, start.y
        counter = len(q)
        while q:
            _, _, current = heapq.heappop(q)
            if current == start:
                self.finished = True
                break
            if ct.get_cpu_time_elapsed() > MoveHeapAstar.CPU_BUDGET:
                self.finished = False
                return None

            ci = (current.y + pad) * pad_w + (current.x + pad)
            cur_dist = dist[ci]
            for dx, dy in dir8_delta:
                nx = current.x + dx
                ny = current.y + dy
                if nx < 0 or nx >= w or ny < 0 or ny >= h:
                    continue
                idx = ci + dy * pad_w + dx
                if dist[idx] is not INF:
                    continue
                move_cost = cost[idx]
                if move_cost is INF:
                    continue
                new_dist = cur_dist + move_cost
                dist[idx] = new_dist
                bd = bfs_dist[ny * w + nx]
                if bd < INF:
                    f = new_dist + bd
                else:
                    f = new_dist + max(abs(ny - sy), abs(nx - sx))
                heapq.heappush(q, (f, counter, Position(nx, ny)))
                counter += 1
        else:
            self.finished = True
            return None

        path: list[Position] = []
        current = start
        while current != target:
            if current in path:
                break
            path.append(current)
            best_dist = INF
            best = current
            ci = (current.y + pad) * pad_w + (current.x + pad)
            for dx, dy in dir8_delta:
                nx = current.x + dx
                ny = current.y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                idx = ci + dy * pad_w + dx
                d = dist[idx]
                if d is not INF and cost[idx] is not INF and d < best_dist:
                    best_dist = d
                    best = Position(nx, ny)
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
        cost = b.cost_grid
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
