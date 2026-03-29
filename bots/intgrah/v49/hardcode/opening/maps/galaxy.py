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

# galaxy (40x40), ROT symmetry
# Core A: (4, 35), Core B: (35, 4)
# Ti: (8,35) dist=4, (6,29) dist=6
# Ax: (15,31) dist=11
#
# Econ opening with full foundry pipeline.
# B2 (turn 1): walks NE to Ax (15,31) via conveyors along row 31.
# B1 (turn 2): Ti harvester (8,35) bridges to core; Ti (6,29) bridges to foundry.
# Foundry at (5,31); refined Ax bridges to core (4,34).

_B2: list[DslTurn] = [
    NE.rd(),
    NE.rd(),
    E.rd(),
    c(NE, W) | NE,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(E) | None,
    ba(NE) | None,
    ba(SE) | None,
    W.turn(),
    ba(S) | None,
    W.turn(),
    W.turn(),
    ba(S) | None,
    W.turn(),
    W.turn(),
    ba(S) | None,
    W.turn(),
    SW.turn(),
    ba(E) | None,
    ba(SE) | None,
    ba(SW) | None,
    *[wait] * 10,
]

_B1: list[DslTurn] = [
    E.rd(),
    br(SE, (-2, 0)) | None,
    E.rd(),
    h(SE) | None,
    ln(SW) | None,
    N.rd(),
    N.turn(),
    br(N, (-2, 0)) | None,
    NW.rd(),
    NW.rd(),
    br(N, (0, 2)) | None,
    h(NE) | None,
    br(SW, (0, 3)) | None,
    *[wait] * 6,
    f(S) | None,
    ba(E) | None,
    ba(NW) | None,
    ba(W) | None,
    *[wait] * 12,
]

register(
    KnownMap.GALAXY,
    Opening(
        core_spawns=[(0, -1), (1, -1)],
        builder_scripts=[_B2, _B1],
    ),
)
