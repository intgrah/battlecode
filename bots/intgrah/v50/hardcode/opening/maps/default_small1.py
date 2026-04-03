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
    h(N),
    NE.rd(),
    ba(NE),
    ba(E),
    ba(SE) | SW,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S),
    ln(NE),
]

_B2: list[DslTurn] = [
    sp(SE, N) | SE,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(E),
    ba(SE),
    ln(S) | NE,
    ba(SE) | E,
    ba(SE) | E,
    E.rd(),
    NE,
]

_B3: list[DslTurn] = [
    sn(SW, S) | S,
    S,
    S,
    E.rd(),
    E.rd(),
    SE.rd(),
    SE.rd(),
    sn(NE, SE),
    E.rd(),
    sn(W, SE),
    NE.rd(),
]

register(
    KnownMap.DEFAULT_SMALL1,
    Opening(
        core_spawns=[(1, 1), (0, 1), (1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
