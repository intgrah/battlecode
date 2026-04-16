from __future__ import annotations

import heapq
from typing import TYPE_CHECKING, Final

from cambc import Controller, Position
from util import INF

if TYPE_CHECKING:
    from builder import Builder


class MoveHeapAstar:
    CPU_BUDGET: Final = 1729
    TARGET_DRIFT_SQ: Final = 25

    def __init__(self, builder: Builder) -> None:
        self.builder = builder
        n = builder.w * builder.h
        self.dist: list[int] = [INF] * n
        self.dist_reset: Final[tuple[int, ...]] = (INF,) * n
        self.q: list[tuple[int, int]] = []
        self.finished = True
        self.target: Position | None = None

    def search(
        self,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> list[Position] | None:
        b = self.builder
        w = b.w
        cost_grid = b.cost_grid
        bfs_dist = b.bfs_dist
        pnb = b.pnb

        si = start.y * w + start.x
        gi = target.y * w + target.x

        if (
            self.finished
            or self.target is None
            or target.distance_squared(self.target) > MoveHeapAstar.TARGET_DRIFT_SQ
        ):
            self.dist[:] = self.dist_reset
            self.q.clear()
            gi = target.y * w + target.x
        else:
            target = self.target
            gi = target.y * w + target.x

        self.target = target
        dist = self.dist
        q = self.q

        if bfs_dist[gi] is INF:
            self.finished = True
            return None

        if dist[gi] is INF:
            dist[gi] = 0
            heapq.heappush(q, (0, gi))

        while q:
            _, node = heapq.heappop(q)
            if node == si:
                self.finished = True
                break
            if ct.get_cpu_time_elapsed() > MoveHeapAstar.CPU_BUDGET:
                self.finished = False
                return None

            cur_dist = dist[node]
            for ni in pnb[node]:
                if dist[ni] is not INF:
                    continue
                mc = cost_grid[ni]
                if mc >= INF:
                    continue
                new_dist = cur_dist + mc
                dist[ni] = new_dist
                heapq.heappush(q, (new_dist + bfs_dist[ni], ni))
        else:
            self.finished = True
            return None

        path: list[int] = [si]
        node = si
        cur_d = dist[si]
        while node != gi:
            best_dist = cur_d
            best = node
            for ni in pnb[node]:
                d = dist[ni]
                if d is not INF and d < best_dist:
                    best_dist = d
                    best = ni
            if best == node:
                return None
            path.append(best)
            node = best
            cur_d = best_dist

        return [Position(i % w, i // w) for i in path]

    def search_blocked(
        self,
        ct: Controller,
        start: Position,
        goal: Position,
    ) -> list[Position] | None:
        b = self.builder
        cost = b.cost_grid
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
