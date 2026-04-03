from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    NW,
    SE,
    SW,
    DslTurn,
    E,
    N,
    S,
    W,
    ba,
    br,
    c,
    h,
    ln,
    sn,
    sp,
    wait,
)

_B1: list[DslTurn] = [
    sp(S, N) | S,
    S.rd(),
    S.rd(),
    br(S, (0, -3)) | S,
    S.rd(),
    S.rd(),
    br(S, (0, -3)) | S,
    c(W, E) | W,
    h(W) | E,
    c(E, W) | E,
    h(E),
    c(N, S) | N,
    E.rd(),
    E.rd(),
    br(E, (-3, 0)) | E,
    h(E),
    NE.rd(),
    br(E, (-2, 1)) | E,
    *[wait] * 20,
    h(E),
]

_B2: list[DslTurn] = [
    NE.rd(),
    br(NE, (-2, 2)) | NE,
    h(N),
    ba(NE),
    NW.rd(),
    ba(NE),
    SE | ba(NW),
    ln(W) | SW,
    SW,
    S,
    S,
    sn(S, SE) | SW,
    *[wait] * 4,
]

_B3: list[DslTurn] = []

register(
    KnownMap.DEFAULT_LARGE2,
    Opening(
        core_spawns=[(0, 1), (1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
