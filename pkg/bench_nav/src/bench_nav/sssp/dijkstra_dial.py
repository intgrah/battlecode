from __future__ import annotations

from collections import deque
from typing import Final

from bench_nav.common import CE, INF
from bench_nav.precompute import COST, PNB
from bench_nav.types import AlgoName, CostUnit, PrecompCtx, SsspAlgo

assert CE + 1 == 4


def _solve(ctx: PrecompCtx, start: int) -> list[int]:
    n = ctx.n
    cost = ctx[COST]
    pnb = ctx[PNB]
    dist = [INF] * n
    dist[start] = 0
    bk = [deque[int]() for _ in range(4)]
    bk[0].append(start)
    cur_d = 0
    emp = 0
    while emp < 4:
        bki = bk[cur_d & 0b11]
        if bki:
            emp = 0
            popleft = bki.popleft
            while bki:
                node = popleft()
                if dist[node] != cur_d:
                    continue
                for nb in pnb[node]:
                    nd = cur_d + cost[nb]
                    if nd < dist[nb]:
                        dist[nb] = nd
                        bk[nd & 0b11].append(nb)
        else:
            emp += 1
        cur_d += 1
    return dist


ALGO: Final[SsspAlgo] = SsspAlgo(
    name=AlgoName("dijkstra-dial"),
    requires=frozenset({COST, PNB}),
    unit=CostUnit.COST,
    solve=_solve,
)
