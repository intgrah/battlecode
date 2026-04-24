from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import INF, Path_, extract_parent
from bench_nav.precomputation import PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)


class BiBfs(Spsp):
    REQUIRES = frozenset({PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb = ctx[PNB]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        pnb = self.pnb
        n = self.n
        parent_f = [-1] * n
        parent_b = [-1] * n
        dist_f = [INF] * n
        dist_b = [INF] * n
        parent_f[start] = start
        parent_b[goal] = goal
        dist_f[start] = 0
        dist_b[goal] = 0
        qf = deque([start])
        qb = deque([goal])
        best = INF
        meet = -1
        while qf or qb:
            min_remaining = 0
            if qf:
                min_remaining += dist_f[qf[0]]
            if qb:
                min_remaining += dist_b[qb[0]]
            if min_remaining >= best:
                break
            if qf and (not qb or len(qf) <= len(qb)):
                node = qf.popleft()
                d = dist_f[node] + 1
                for nb in pnb[node]:
                    if dist_f[nb] <= d:
                        continue
                    dist_f[nb] = d
                    parent_f[nb] = node
                    qf.append(nb)
                    if dist_b[nb] is not INF and d + dist_b[nb] < best:
                        best = d + dist_b[nb]
                        meet = nb
            elif qb:
                node = qb.popleft()
                d = dist_b[node] + 1
                for nb in pnb[node]:
                    if dist_b[nb] <= d:
                        continue
                    dist_b[nb] = d
                    parent_b[nb] = node
                    qb.append(nb)
                    if dist_f[nb] is not INF and dist_f[nb] + d < best:
                        best = dist_f[nb] + d
                        meet = nb
        if meet < 0:
            return None
        path = extract_parent(parent_f, start, meet)
        if path is None:
            return None
        if meet != goal:
            cur = parent_b[meet]
            while cur != goal:
                path.append(cur)
                cur = parent_b[cur]
            path.append(goal)
        return path
