from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    SE,
    SW,
    DslTurn,
    E,
    N,
    S,
    W,
    ba,
    c,
    h,
    ln,
    sn,
    sp,
)

_B1: list[DslTurn] = [
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(N) | None,
    NE.rd(),
    ba(NE) | None,
    ba(E) | None,
    ba(SE) | SW,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S) | None,
    ln(NE) | None,
]

_B2: list[DslTurn] = [
    sp(SE, N) | SE,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(E) | None,
    ba(SE) | None,
    ln(S) | NE,
    ba(SE) | E,
    ba(SE) | E,
    E.rd(),
    NE.turn(),
]

_B3: list[DslTurn] = [
    sn(SW, S) | S,
    S.turn(),
    S.turn(),
    E.rd(),
    E.rd(),
    SE.rd(),
    SE.rd(),
    sn(NE, SE) | None,
    E.rd(),
    sn(W, SE) | None,
    NE.rd(),
]

register(
    KnownMap.DEFAULT_SMALL1,
    Opening(
        core_spawns=[(1, 1), (0, 1), (1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
