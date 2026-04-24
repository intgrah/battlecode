from __future__ import annotations

from typing import override

from bench_nav.precomputation import APSP, COST, PNB
from bench_nav.types import PrecompCtx, Spsp


class AstarBase(Spsp):
    REQUIRES = frozenset({COST, PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]


class AstarApspBase(AstarBase):
    REQUIRES = frozenset({COST, PNB, APSP})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        super().__init__(ctx)
        self.apsp_cols = ctx[APSP]
