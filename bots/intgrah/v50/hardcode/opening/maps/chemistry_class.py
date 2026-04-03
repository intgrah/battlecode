from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    NW,
    SW,
    DslTurn,
    E,
    N,
    S,
    W,
    br,
    c,
    f,
    h,
    sn,
    sp,
    wait,
)

_B1: list[DslTurn] = [
    sp(N, S) | N,
    c(N, S) | N,
    c(N, S) | N,
    c(W, E) | W,
    NW.rd(),
    br(NW, (2, 2)),
    h(W),
    h(N) | NW,
    h(W),
    # wait for income
    *[wait] * 20,
    h(N),
    sn(NE, NE),
    NW.rd(),
    N.rd(),
    N.rd(),
    NW.rd(),
    br(NW, (0, -3)) | NW,
    NE.rd(),
    N.rd(),
    c(NW, E) | NW,
    NE.rd(),
    E.rd(),
    br(NE, (-2, 2)),
    f(SW) | NE,
    h(W),
    h(N),
    h(E),
]


_B2: list[DslTurn] = [
    sp(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    SW.rd(),
    br(SW, (2, -2)) | SW,
    h(S),
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    *[wait] * 48,
    h(S),
    c(W, E) | W,
    c(W, E) | W,
    c(S, N) | S,
    *[wait] * 12,
    h(W),
    *[wait] * 12,
    h(S),
]

# Defense
_B3: list[DslTurn] = [
    S.rd(),
    S.rd(),
    S.rd(),
    S.rd(),
    S.rd(),
    SW.rd(),
    SW.rd(),
]

register(
    KnownMap.CHEMISTRY_CLASS,
    Opening(
        core_spawns=[
            (-1, -1),
            (-1, 1),
            (1, 1),
        ],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
