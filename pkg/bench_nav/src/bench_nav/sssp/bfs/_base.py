from __future__ import annotations

from typing import ClassVar, override

from bench_nav.precomputation import PNB, PNB_SKIP
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class BfsBase(Sssp):
    UNIT = CostUnit.HOPS
    SKIP: ClassVar[bool] = False

    @override
    def __init_subclass__(cls, **kw: object) -> None:
        super().__init_subclass__(**kw)
        if "REQUIRES" not in cls.__dict__:
            cls.REQUIRES = frozenset({PNB_SKIP}) if cls.SKIP else frozenset({PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        if self.SKIP:
            self.pnb_push, self.pnb_set = ctx[PNB_SKIP]
        else:
            self.pnb = ctx[PNB]
