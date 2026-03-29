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
    f,
    gn,
    h,
    ln,
    sn,
    sp,
    wait,
)

_B1: list[DslTurn] = [
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(SE, N) | SE,
    sn(E, E) | None,
    h(SE) | None,
    c(S, N) | S,
    SE.rd(),
    ln(NE) | None,
    sn(SE, NE) | None,
    h(S) | None,
]

_B2: list[DslTurn] = [
    NE.turn(),
    E.turn(),
    E.turn(),
    c(E, W) | E,
    h(E) | None,
    sn(NE, E) | None,
    N.rd(),
    ln(NE) | None,
]

_B3: list[DslTurn] = [
    E.turn(),
    E.turn(),
    E.turn(),
    wait,
    SE.turn(),
    S.turn(),
    c(S, N) | S,
    c(S, N) | S,
]


register(
    KnownMap.BATTLEBOT,
    Opening(
        core_spawns=[(1, 0), (1, 1), (1, 0)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
