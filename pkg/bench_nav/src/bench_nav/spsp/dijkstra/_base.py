from __future__ import annotations

from typing import override

from bench_nav.precomputation import COST, PNB
from bench_nav.types import PrecompCtx, Spsp


class DijkstraBase(Spsp):
    REQUIRES = frozenset({COST, PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]
