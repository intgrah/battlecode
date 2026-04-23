from __future__ import annotations

from collections import deque
from typing import Final

from bench_nav.common import INF
from bench_nav.map_data import (
    build_nb,
    build_pnb,
    build_pnb_dual,
    build_pnb_navbfs,
    build_pnb_navdijkstra,
    build_pnbc,
    build_pnbc_navdijkstra,
)
from bench_nav.map_data_jps import (
    build_dir_of_offset,
    build_pnb_by_offset,
    build_pnb_dir,
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


def _pnb_navbfs(ctx: PrecompCtx) -> tuple[list[list[int]], list[list[int]]]:
    return build_pnb_navbfs(ctx.w, ctx.h, ctx[COST])


PNB_NAVBFS: Final[Precomp[tuple[list[list[int]], list[list[int]]]]] = Precomp(
    label="pnb_navbfs",
    deps=frozenset({COST}),
    availability=Availability.FULL_MAP,
    compute=_pnb_navbfs,
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
