from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    NW,
    SE,
    DslTurn,
    E,
    N,
    S,
    W,
    ba,
    br,
    c,
    h,
    sn,
)

_B1: list[DslTurn] = [
    c(SE, N) | SE,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S) | None,
    ba(SE) | None,
    ba(E) | None,
]

_B2: list[DslTurn] = [
    c(SE, E) | SE,
    c(N, S) | N,
    c(N, S) | N,
    ba(SE) | None,
    ba(E) | None,
    ba(NE) | None,
    c(N, S) | N,
    c(N, S) | N,
    NE.rd(),
    br(NW, (0, 2)) | NW,
    h(N) | None,
]

_B3: list[DslTurn] = [
    c(E, N) | E,
    sn(NE, E) | W,
    W.turn(),
    W.turn(),
    c(W, E) | W,
    c(W, E) | W,
    h(W) | None,
]


register(
    KnownMap.FACE,
    Opening(
        core_spawns=[(1, 1), (1, -1), (1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
