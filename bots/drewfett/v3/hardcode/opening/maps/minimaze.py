from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
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
    ln,
    sn,
)

_B1: list[DslTurn] = [
    c(NE, W) | NE,
    *[c(E, W) | E] * 7,
    h(E) | None,
    h(SE) | None,
    c(S, N) | None,
    ba(N) | None,
    sn(NE, N) | None,
]

_B2: list[DslTurn] = [
    NE.rd(),
    NE.rd(),
    E.rd(),
    E.rd(),
    br(E, (0, 2)) | None,
    h(NE) | W,
    ln(NE) | W,
    W.rd(),
]

register(
    KnownMap.MINIMAZE,
    Opening(
        core_spawns=[(1, 0), (1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
