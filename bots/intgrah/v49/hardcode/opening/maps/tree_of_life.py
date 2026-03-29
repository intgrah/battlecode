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

# tree_of_life: 39x30, VER symmetry (E<->W reflection)
# Core A at (4,22), Core B at (34,22)

# B1: Ti harvester at (8,25) -> bridge to core
# Spawn offset (1,-1) -> pos (5,21)
_B1: list[DslTurn] = [
    E.rd(),
    SE.rd(),
    SE.rd(),
    E.rd(),
    SE.rd(),
    S.rd(),
    SW.rd(),
    h(NW) | None,
    ba(N) | None,
    ba(W) | None,
    S.rd(),
    W.rd(),
    W.rd(),
    NW.rd(),
    N.rd(),
    # bridge at E=(7,25), target core(5,23), vec=(-2,-2)
    br(E, (-2, -2)) | None,
    ln(N) | None,
]

# B2: Ax pipeline
# Spawn offset (-1,-1) -> pos (3,21)
_B2: list[DslTurn] = [
    NW.rd(),
    NW.rd(),
    N.rd(),
    NW.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    N.rd(),
    NE.rd(),
    NE.rd(),
    N.rd(),
    NE.rd(),
    c(NE, N) | NE,
    c(E, W) | E,
    h(NE) | None,
    ba(N) | None,
    c(E, W) | E,
    ba(NE) | None,
    W.turn(),
    W.turn(),
    h(S) | None,
    ba(SE) | None,
    *[wait] * 10,
    f(N) | None,
    ln(NW) | None,
    c(NW, S) | None,
    c(W, S) | W,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
    c(S, S) | S,
]

register(
    KnownMap.TREE_OF_LIFE,
    Opening(
        core_spawns=[(1, -1), (-1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
