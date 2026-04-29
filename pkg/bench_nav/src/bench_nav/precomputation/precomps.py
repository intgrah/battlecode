from __future__ import annotations

from collections import deque
from typing import Final

from bench_nav.common import INF
from bench_nav.precomputation.map_data import (
    build_dir_of_offset,
    build_nb,
    build_pnb,
    build_pnb_by_offset,
    build_pnb_dir,
    build_pnb_dual,
    build_pnb_fd,
    build_pnb_navdijkstra,
    build_pnb_skip,
    build_pnbc,
    build_pnbc_navdijkstra,
)
from bench_nav.types import Availability, Precomp, PrecompCtx


def _seeded(label: str) -> Precomp[list[int]]:
    def _fail(_: PrecompCtx) -> list[int]:
        msg = f"{label} is a seeded leaf; it must be placed on the context before resolve()"
        raise RuntimeError(msg)

    return Precomp(
        label=label,
        deps=frozenset(),
        availability=Availability.FULL_MAP,
        compute=_fail,
    )


TILES: Final[Precomp[list[int]]] = _seeded("tiles")
COST: Final[Precomp[list[int]]] = _seeded("cost")

NB: Final[Precomp[list[list[int]]]] = Precomp(
    label="nb",
    deps=frozenset(),
    availability=Availability.STATIC,
    compute=lambda ctx: build_nb(ctx.w, ctx.h),
)

PNB: Final[Precomp[list[list[int]]]] = Precomp(
    label="pnb",
    deps=frozenset({NB, COST}),
    availability=Availability.FULL_MAP,
    compute=lambda ctx: build_pnb(ctx[NB], ctx[COST]),
)

PNB_FD: Final[Precomp[list[list[int]]]] = Precomp(
    label="pnb_fd",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=lambda ctx: build_pnb_fd(ctx.w, ctx.h, ctx[COST]),
)

PNBC: Final[Precomp[list[list[tuple[int, int]]]]] = Precomp(
    label="pnbc",
    deps=frozenset({NB, COST}),
    availability=Availability.FULL_MAP,
    compute=lambda ctx: build_pnbc(ctx[NB], ctx[COST]),
)


def _pnb_dual(ctx: PrecompCtx) -> tuple[list[list[int]], list[list[int]]]:
    return build_pnb_dual(ctx[NB], ctx[COST])


PNB_DUAL: Final[Precomp[tuple[list[list[int]], list[list[int]]]]] = Precomp(
    label="pnb_dual",
    deps=frozenset({NB, COST}),
    availability=Availability.FULL_MAP,
    compute=_pnb_dual,
)


def _pnb_skip(ctx: PrecompCtx) -> tuple[list[list[int]], list[list[int]]]:
    return build_pnb_skip(ctx.w, ctx.h, ctx[COST])


PNB_SKIP: Final[Precomp[tuple[list[list[int]], list[list[int]]]]] = Precomp(
    label="pnb_skip",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=_pnb_skip,
)


def _pnb_navdijkstra(ctx: PrecompCtx) -> tuple[list[list[int]], list[list[int]]]:
    return build_pnb_navdijkstra(ctx.w, ctx.h, ctx[COST])


PNB_NAVDIJKSTRA: Final[Precomp[tuple[list[list[int]], list[list[int]]]]] = Precomp(
    label="pnb_navdijkstra",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=_pnb_navdijkstra,
)


def _pnbc_navdijkstra(
    ctx: PrecompCtx,
) -> tuple[list[list[tuple[int, int]]], list[list[tuple[int, int]]]]:
    return build_pnbc_navdijkstra(ctx.w, ctx.h, ctx[COST])


PNBC_NAVDIJKSTRA: Final[
    Precomp[tuple[list[list[tuple[int, int]]], list[list[tuple[int, int]]]]]
] = Precomp(
    label="pnbc_navdijkstra",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=_pnbc_navdijkstra,
)


PNB_DIR: Final[Precomp[list[list[list[int]]]]] = Precomp(
    label="pnb_dir",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=lambda ctx: build_pnb_dir(ctx.w, ctx.h, ctx[COST]),
)

PNB_BY_OFFSET: Final[Precomp[list[list[list[int]]]]] = Precomp(
    label="pnb_by_offset",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=lambda ctx: build_pnb_by_offset(ctx.w, ctx.h, ctx[COST]),
)

DIR_OF_OFFSET: Final[Precomp[list[int]]] = Precomp(
    label="dir_of_offset",
    deps=frozenset(),
    availability=Availability.STATIC,
    compute=lambda ctx: build_dir_of_offset(ctx.w),
)


def _apsp(ctx: PrecompCtx) -> list[list[int]]:
    """All-pairs shortest paths via Dial's buckets, stored column-major.

    Returns cols where cols[target][source] = weighted dist from source to
    target. Column indexing gives O(1) slice access to "dist to goal" from
    any source, which is what A* heuristics want.
    """
    n = ctx.n
    cost = ctx[COST]
    pnb = ctx[PNB]
    rows: list[list[int]] = []
    for start in range(n):
        if cost[start] >= INF:
            rows.append([INF] * n)
            continue
        dist: list[int] = [INF] * n
        dist[start] = 0
        bk: list[deque[int]] = [deque() for _ in range(4)]
        bk[0].append(start)
        cur_d = 0
        gap = 0
        while gap < 4:
            bki = bk[cur_d & 3]
            if not bki:
                cur_d += 1
                gap += 1
                continue
            gap = 0
            node = bki.popleft()
            if dist[node] != cur_d:
                continue
            for nb in pnb[node]:
                nd = cur_d + cost[nb]
                if nd < dist[nb]:
                    dist[nb] = nd
                    bk[nd & 3].append(nb)
        rows.append(dist)
    return [[rows[i][j] for i in range(n)] for j in range(n)]


APSP: Final[Precomp[list[list[int]]]] = Precomp(
    label="apsp",
    deps=frozenset({COST, PNB}),
    availability=Availability.FULL_MAP,
    compute=_apsp,
)


def bfs_dist(pnb: list[list[int]], n: int, start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q: deque[int] = deque((start,))
    while q:
        node = q.popleft()
        d1 = dist[node] + 1
        for nb in pnb[node]:
            if dist[nb] == INF:
                dist[nb] = d1
                q.append(nb)
    return dist


def resolve(required: frozenset[Precomp[object]]) -> tuple[Precomp[object], ...]:
    closure: set[Precomp[object]] = set()
    stack: list[Precomp[object]] = list(required)
    while stack:
        p = stack.pop()
        if p in closure:
            continue
        closure.add(p)
        stack.extend(p.deps)

    order: list[Precomp[object]] = []
    visited: set[Precomp[object]] = set()
    temp: set[Precomp[object]] = set()

    def visit(p: Precomp[object]) -> None:
        if p in visited:
            return
        if p in temp:
            msg = f"cycle at {p.label}"
            raise ValueError(msg)
        temp.add(p)
        for d in p.deps:
            if d in closure:
                visit(d)
        temp.remove(p)
        visited.add(p)
        order.append(p)

    for p in closure:
        visit(p)
    return tuple(order)


def build_ctx(
    w: int,
    h: int,
    tiles: list[int],
    cost: list[int],
    order: tuple[Precomp[object], ...],
) -> PrecompCtx:
    ctx = PrecompCtx(w=w, h=h, n=w * h)
    ctx.put(TILES, tiles)
    ctx.put(COST, cost)
    for p in order:
        if p is TILES or p is COST:
            continue
        ctx.put(p, p.compute(ctx))
    return ctx
