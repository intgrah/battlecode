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
    sn,
    sp,
    wait,
)

_B1: list[DslTurn] = [
    sp(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    NE.rd(),
    br(NE, (-2, 2)) | NE,
    c(E, W) | E,
    h(E) | None,
    ba(SE) | None,
    NE.rd(),
    ba(SE) | None,
    SW | ba(NE),
    NW.turn(),
    NW.turn(),
    NE.turn(),
    c(N, S) | N,
    c(N, S) | N,
    c(N, S) | N,
    h(W) | None,
    ba(N) | None,
    ba(E) | None,
    ba(SW) | None,
]


_B2: list[DslTurn] = [
    NE.rd(),
    NE.rd(),
    NE.rd(),
    NE.rd(),
    NE.rd(),
    N.rd(),
    NE.rd(),
    NE.rd(),
    sn(S, N) | None,
    ba(E) | None,
]

_B3: list[DslTurn] = [
    E.turn(),
    E.turn(),
    E.turn(),
    E.turn(),
    E.turn(),
    E.turn(),
    E.turn(),
    NE.turn(),
    NE.turn(),
    N.rd(),
    NW.rd(),
    br(NE, (0, 3)) | NE,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(N) | None,
    NE.rd(),
    ba(NW) | None,
    SW | ba(NE),
    ba(E) | W,
    ln(N) | W,
]

_B4: list[DslTurn] = [
    sn(E, E) | NE,
    sn(N, NW) | E,
    E.turn(),
    E.turn(),
    ln(N) | E,
    E.turn(),
    SE.rd(),
    ba(E) | None,
    ba(SE) | NW,
]

register(
    KnownMap.CINNAMON_ROLL,
    Opening(
        core_spawns=[(1, 0), (1, -1), (1, 0), *[None] * 60, (1, 1)],
        builder_scripts=[_B1, _B2, _B3, _B4],
    ),
)
