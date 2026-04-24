from __future__ import annotations

from typing import override

from bench_nav.common import INF
from bench_nav.precomputation import COST
from bench_nav.types import CostUnit, PrecompCtx, Sssp


class BfsBitmap(Sssp):
    REQUIRES = frozenset({COST})
    UNIT = CostUnit.HOPS

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.n = ctx.n
        self.w = ctx.w
        cost = ctx[COST]
        n = self.n
        w = self.w
        h = ctx.h
        passable = 0
        for i in range(n):
            if cost[i] < INF:
                passable |= 1 << i
        not_east = 0
        not_west = 0
        for y in range(h):
            for x in range(w):
                i = y * w + x
                if x != w - 1:
                    not_east |= 1 << i
                if x != 0:
                    not_west |= 1 << i
        self.passable = passable
        self.not_east = not_east
        self.not_west = not_west
        self.full_mask = (1 << n) - 1

    @override
    def solve(self, start: int) -> list[int]:
        n = self.n
        w = self.w
        passable = self.passable
        not_east = self.not_east
        not_west = self.not_west
        full_mask = self.full_mask
        dist = [INF] * n
        dist[start] = 0
        frontier = 1 << start
        visited = frontier
        d = 1
        while frontier:
            e = (frontier & not_east) << 1
            w_ = (frontier & not_west) >> 1
            n_ = frontier >> w
            s_ = (frontier << w) & full_mask
            ne = (n_ & not_east) << 1
            nw = (n_ & not_west) >> 1
            se = (s_ & not_east) << 1
            sw = (s_ & not_west) >> 1
            expanded = e | w_ | n_ | s_ | ne | nw | se | sw
            frontier = expanded & passable & ~visited
            b = frontier
            while b:
                lsb = b & -b
                dist[lsb.bit_length() - 1] = d
                b ^= lsb
            visited |= frontier
            d += 1
        return dist
