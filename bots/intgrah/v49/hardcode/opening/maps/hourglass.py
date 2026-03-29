from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    DslTurn,
    E,
    N,
    S,
    W,
    br,
    c,
    h,
    sn,
    wait,
)

_B1: list[DslTurn] = [
    *[c(N, S) | N] * 15,
    h(NE) | None,
    sn(N, N) | None,
    c(E, W) | None,
    *[wait] * 15,
]

_B2: list[DslTurn] = [
    NE.turn(),
    N.turn(),
    N.turn(),
    br(E, (0, 3)) | E,
    h(N) | None,
    c(E, W) | E,
    h(N) | W,
    W.turn(),
    br(W, (0, 3)) | W,
    h(N) | None,
    c(W, E) | W,
    h(N) | E,
    NE.turn(),
    N.turn(),
    N.turn(),
    N.turn(),
    N.turn(),
    *[wait] * 12,
    h(W) | N,
]


register(
    KnownMap.HOURGLASS,
    Opening(
        core_spawns=[(0, -1), (-1, -1), *[None] * 16],
        builder_scripts=[_B1, _B2],
    ),
)
