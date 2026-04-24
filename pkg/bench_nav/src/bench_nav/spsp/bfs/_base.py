from __future__ import annotations

from typing import override

from bench_nav.precomputation import COST, PNB, PNB_SKIP
from bench_nav.types import PrecompCtx, Spsp


class BfsSkipBase(Spsp):
    REQUIRES = frozenset({COST, PNB, PNB_SKIP})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]
        self.pnb_push, self.pnb_set = ctx[PNB_SKIP]
