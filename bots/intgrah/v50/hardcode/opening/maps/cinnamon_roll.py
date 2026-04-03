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
)

_B1: list[DslTurn] = [
    sp(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    NE.rd(),
    br(NE, (-2, 2)) | NE,
    c(E, W) | E,
    h(E),
    ba(SE),
    NE.rd(),
    ba(SE),
    SW | ba(NE),
    NW,
    NW,
    NE,
    c(N, S) | N,
    c(N, S) | N,
    c(N, S) | N,
    h(W),
    ba(N),
    ba(E),
    ba(SW),
]


_B2: list[DslTurn] = [
    NE.rd(),
    NE.rd(),
    NE.rd(),
    NE.rd(),
    NE.rd(),
    N.rd(),
    NE.rd(),
    NE.rd(),
    sn(S, N),
    ba(E),
]

_B3: list[DslTurn] = [
    E,
    E,
    E,
    E,
    E,
    E,
    E,
    NE,
    NE,
    N.rd(),
    NW.rd(),
    br(NE, (0, 3)) | NE,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(N),
    NE.rd(),
    ba(NW),
    SW | ba(NE),
    ba(E) | W,
    ln(N) | W,
]

_B4: list[DslTurn] = [
    sn(E, E) | NE,
    sn(N, NW) | E,
    E,
    E,
    ln(N) | E,
    E,
    SE.rd(),
    ba(E),
    ba(SE) | NW,
]

register(
    KnownMap.CINNAMON_ROLL,
    Opening(
        core_spawns=[(1, 0), (1, -1), (1, 0), *[None] * 60, (1, 1)],
        builder_scripts=[_B1, _B2, _B3, _B4],
    ),
)
