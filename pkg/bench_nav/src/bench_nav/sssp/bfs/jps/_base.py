from __future__ import annotations

from typing import override

from bench_nav.precomputation import DIR_OF_OFFSET, PNB_BY_OFFSET, PNB_DIR
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class JpsDirBase(Sssp):
    REQUIRES = frozenset({PNB_DIR, DIR_OF_OFFSET})
    UNIT = CostUnit.HOPS

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb_dir = ctx[PNB_DIR]
        self.dir_of_offset = ctx[DIR_OF_OFFSET]


class JpsOffsetBase(Sssp):
    REQUIRES = frozenset({PNB_BY_OFFSET})
    UNIT = CostUnit.HOPS

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.pnb_by_offset = ctx[PNB_BY_OFFSET]
