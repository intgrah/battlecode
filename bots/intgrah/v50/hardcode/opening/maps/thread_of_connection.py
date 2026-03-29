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
    ba(NE) | None,
    br(W, (0, 3)) | W,
    c(N, S) | N,
    h(E) | None,
    sn(NE, NW) | None,
    c(W, E) | W,
    c(N, S) | N,
    NW.rd(),
    NW.rd(),
    NE.rd(),
    ba(NE) | None,
    ba(N) | None,
    ba(NW) | None,
    W.rd(),
    ba(NW) | None,
]

_B2: list[DslTurn] = [
    NE | h(E),
    NE | h(NE),
    h(E) | N,
    h(N) | None,
    ln(SW) | None,
    ba(NE) | S,
    SE.rd(),
    NE.rd(),
    ba(N) | SW,
    ba(NE) | None,
    ba(E) | None,
    ba(SW) | None,
    NW | ba(SE),
    N.turn(),
    NW.turn(),
    NW.turn(),
    wait,
]

register(
    KnownMap.THREAD_OF_CONNECTION,
    Opening(
        core_spawns=[(1, -1), (1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
