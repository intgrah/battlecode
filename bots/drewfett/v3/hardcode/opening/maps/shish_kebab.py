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
)

_B1: list[DslTurn] = [
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(E, W) | E,
    h(E) | None,
]

_B2: list[DslTurn] = [
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(E) | None,
    SE.rd(),
    ba(NE) | None,
    ln(W) | None,
    br(SE, (-2, -2)) | SE,
    SE.rd(),
    br(E, (-2, -1)) | E,
    h(E) | None,
]

register(
    KnownMap.SHISH_KEBAB,
    Opening(
        core_spawns=[(1, 1), (1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
