from __future__ import annotations

from typing import override

from bench_nav.precomputation import COST, PNB
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class DijkstraBase(Sssp):
    REQUIRES = frozenset({COST, PNB})
    UNIT = CostUnit.COST

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]
