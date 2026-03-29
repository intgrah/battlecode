from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
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
)

# landscape
# Core A at (3, 1)

# B1: spawn (-1,0) => (2,2) [sic, offset from core center]
_B1: list[DslTurn] = [
    c(W, E) | W,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    SE.rd(),
    S.rd(),
    c(W, N) | W,
    # bridge at S=(1,10), target (1,7), vec=(0,-3)
    br(S, (0, -3)) | E,
    S.rd(),
    c(SW, N) | SW,
    h(SE) | None,
    c(S, N) | None,
    ln(NW) | None,
    ba(E) | None,
    S.turn(),
    ba(SE) | None,
]

# B2: spawn (1,0) => (4,2) [sic]
_B2: list[DslTurn] = [
    c(SE, W) | SE,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(SE) | None,
    c(S, W) | S,
    c(S, N) | S,
    h(SE) | None,
    c(S, N) | None,
    N.turn(),
    f(W) | None,
    ln(SW) | None,
    N.turn(),
    ba(E) | None,
    S.turn(),
    ba(SE) | None,
]

register(
    KnownMap.LANDSCAPE,
    Opening(
        core_spawns=[(-1, 0), (1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
