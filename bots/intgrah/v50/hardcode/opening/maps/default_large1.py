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
    h(S),
    SW.rd(),
    *[wait] * 4,
    f(SE),
    br(S, (2, -2)),
    ba(NE),
    S,
    *[wait] * 10,
    ln(N),
    ba(SE),
    ba(S),
]

_B2: list[DslTurn] = [
    S,
    S,
    S | h(S),
    h(SW),
    SE.rd(),
    SW.rd(),
    h(W),
    ba(SW),
    NE | ba(SW),
    NW | ba(SE),
    *[wait] * 4,
    ln(NW),
]


register(
    KnownMap.DEFAULT_LARGE1,
    Opening(
        core_spawns=[(0, 1), (-1, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
