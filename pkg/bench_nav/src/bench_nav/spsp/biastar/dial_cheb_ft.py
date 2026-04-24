from __future__ import annotations

from collections import deque
from typing import override

from bench_nav.common import CE, CR, INF, Path_, extract_parent
from bench_nav.precomputation import COST, PNB
from bench_nav.types import (
    PrecompCtx,
    Spsp,
)


class BiastarDialChebFt(Spsp):
    REQUIRES = frozenset({COST, PNB})

    @override
    def __init__(self, ctx: PrecompCtx) -> None:
        self.w = ctx.w
        self.n = ctx.n
        self.cost = ctx[COST]
        self.pnb = ctx[PNB]

    @override
    def plan(self, start: int, goal: int) -> Path_:
        w = self.w
        n = self.n
        cost = self.cost
        pnb = self.pnb
        sx, sy = start % w, start // w
        gx, gy = goal % w, goal // w
        mod = CE + 2

        g_f: list[int] = [INF] * n
        parent_f: list[int] = [-1] * n
        g_f[start] = 0
        parent_f[start] = start
        h0 = max(abs(sx - gx), abs(sy - gy)) * CR
        bk_f: list[deque[int]] = [deque() for _ in range(mod)]
        bk_f[h0 % mod].append(start)
        cf = h0
        ef = 0

        g_b: list[int] = [INF] * n
        parent_b: list[int] = [-1] * n
        g_b[goal] = 0
        parent_b[goal] = goal
        bk_b: list[deque[int]] = [deque() for _ in range(mod)]
        bk_b[h0 % mod].append(goal)
        cb = h0
        eb = 0

        meet = -1

        while ef < mod or eb < mod:
            if ef < mod and (eb >= mod or cf <= cb):
                bi = cf % mod
                if not bk_f[bi]:
                    cf += 1
                    ef += 1
                    continue
                ef = 0
                node = bk_f[bi].popleft()
                nx, ny = node % w, node // w
                h_node = max(abs(nx - gx), abs(ny - gy)) * CR
                if g_f[node] + h_node != cf:
                    continue
                if g_b[node] is not INF:
                    meet = node
                    break
                gn = g_f[node]
                for nb in pnb[node]:
                    nd = gn + cost[nb]
                    if nd < g_f[nb]:
                        g_f[nb] = nd
                        parent_f[nb] = node
                        nix, niy = nb % w, nb // w
                        h_ni = max(abs(nix - gx), abs(niy - gy)) * CR
                        bk_f[(nd + h_ni) % mod].append(nb)
            elif eb < mod:
                bi = cb % mod
                if not bk_b[bi]:
                    cb += 1
                    eb += 1
                    continue
                eb = 0
                node = bk_b[bi].popleft()
                nx, ny = node % w, node // w
                h_node = max(abs(nx - sx), abs(ny - sy)) * CR
                if g_b[node] + h_node != cb:
                    continue
                if g_f[node] is not INF:
                    meet = node
                    break
                gn = g_b[node]
                c_node = cost[node]
                for nb in pnb[node]:
                    nd = gn + c_node
                    if nd < g_b[nb]:
                        g_b[nb] = nd
                        parent_b[nb] = node
                        nix, niy = nb % w, nb // w
                        h_ni = max(abs(nix - sx), abs(niy - sy)) * CR
                        bk_b[(nd + h_ni) % mod].append(nb)
            else:
                break

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
