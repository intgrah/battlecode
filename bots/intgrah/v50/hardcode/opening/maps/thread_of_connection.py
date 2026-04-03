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
    wait,
)

_B1: list[DslTurn] = [
    c(E, W) | E,
    c(NE, N) | NE,
    br(N, (-2, 2)) | N,
    NW.rd(),
    ba(NE),
    br(W, (0, 3)) | W,
    c(N, S) | N,
    h(E),
    sn(NE, NW),
    c(W, E) | W,
    c(N, S) | N,
    NW.rd(),
    NW.rd(),
    NE.rd(),
    ba(NE),
    ba(N),
    ba(NW),
    W.rd(),
    ba(NW),
]

_B2: list[DslTurn] = [
    NE | h(E),
    NE | h(NE),
    h(E) | N,
    h(N),
    ln(SW),
    ba(NE) | S,
    SE.rd(),
    NE.rd(),
    ba(N) | SW,
    ba(NE),
    ba(E),
    ba(SW),
    NW | ba(SE),
    N,
    NW,
    NW,
    wait,
]

register(
    KnownMap.THREAD_OF_CONNECTION,
    Opening(
        core_spawns=[(1, -1), (1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
