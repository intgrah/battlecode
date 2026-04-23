from __future__ import annotations

from typing import Final

from bench_nav.common import Path_, extract_parent
from bench_nav.precompute import PNB
from bench_nav.types import (
    AlgoName,
    PrecompCtx,
    SensorReading,
    SequentialSpspAlgo,
)


def _bfs(n: int, pnb: list[list[int]], start: int, goal: int) -> Path_:
    parent = [-1] * n
    parent[start] = start
    q = [start]
    append = q.append
    for node in q:
        for nb in pnb[node]:
            if parent[nb] == -1:
                parent[nb] = node
                if nb == goal:
                    return extract_parent(parent, start, goal)
                append(nb)
    return None


def _init(
    ctx: PrecompCtx, _r: SensorReading, start: int, goal: int
) -> tuple[PrecompCtx, Path_]:
    return ctx, _bfs(ctx.n, ctx[PNB], start, goal)


def _step(
    ctx: PrecompCtx, _r: SensorReading, pos: int, goal: int
) -> tuple[PrecompCtx, Path_]:
    return ctx, _bfs(ctx.n, ctx[PNB], pos, goal)


ALGO: Final[SequentialSpspAlgo[PrecompCtx]] = SequentialSpspAlgo(
    name=AlgoName("bfs"),
    requires=frozenset({PNB}),
    init=_init,
    step=_step,
)
