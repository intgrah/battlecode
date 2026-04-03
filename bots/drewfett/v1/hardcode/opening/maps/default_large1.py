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
    h,
    ln,
    wait,
)

_B1: list[DslTurn] = [
    SW.rd(),
    S.rd(),
    br(S, (0, -3)) | S,
    c(W, E) | W,
    W.rd(),
    h(S) | None,
    SW.rd(),
    *[wait] * 4,
    f(SE) | None,
    br(S, (2, -2)) | None,
    ba(NE) | None,
    S.turn(),
    *[wait] * 10,
    ln(N) | None,
    ba(SE) | None,
    ba(S) | None,
]

_B2: list[DslTurn] = [
    S.turn(),
    S.turn(),
    S | h(S),
    h(SW) | None,
    SE.rd(),
    SW.rd(),
    h(W) | None,
    ba(SW) | None,
    NE | ba(SW),
    NW | ba(SE),
    *[wait] * 4,
    ln(NW) | None,
]


register(
    KnownMap.DEFAULT_LARGE1,
    Opening(
        core_spawns=[(0, 1), (-1, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
