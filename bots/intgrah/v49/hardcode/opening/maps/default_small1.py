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

# default_small1 (20x20) ROT symmetry
# Core A: (1,1), Core B: (18,18)

# B1: Ti harvester at (6,1) -> conv chain W -> core
# Spawn (1,-1) at (2,0)
_B1: list[DslTurn] = [
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    ba(SE) | None,
    h(S) | None,
    ba(SW) | None,
    W.turn(),
    SW.rd(),
    SE.rd(),
    ba(E) | None,
    W.rd(),
    W.rd(),
    # bridge at S=(3,3), target core (1,1), vec=(-2,-2)
    br(S, (-2, -2)) | None,
    ln(SW) | None,
    *[wait] * 15,
]

# B2: Full Ax pipeline
# Spawn (-1,1) at (0,2)
_B2: list[DslTurn] = [
    SE.rd(),
    SE.rd(),
    SE.rd(),
    SE.rd(),
    c(SE, N) | SE,
    c(SE, N) | SE,
    h(E) | None,
    ba(NE) | None,
    ba(SE) | None,
    c(N, W) | N,
    NE.rd(),
    SE.rd(),
    ba(S) | None,
    NW.turn(),
    SW.turn(),
    W.turn(),
    NW.turn(),
    # conv(5,5) facing W, bridge(4,5) target (3,3) vec=(-1,-2)
    c(NE, W) | None,
    br(N, (-1, -2)) | None,
    NE.turn(),
    h(SE) | None,
    ba(E) | None,
    *[wait] * 20,
    f(S) | None,
    *[wait] * 5,
]

register(
    KnownMap.DEFAULT_SMALL1,
    Opening(
        core_spawns=[(1, -1), (-1, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
