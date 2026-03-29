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
    c,
    f,
    h,
    ln,
    sn,
    wait,
)

# default_large1: 40x40, ROT symmetry
# Core A at (11, 25), Core 3x3 = (10-12, 24-26)
# Ti at (8,30),(9,30),(10,30) -- dist 5 south
# Ax at (9,31) -- dist 6 south

# B1: Ti harvester + conv chain to core
# Spawn (0,1) => (11,26)
_B1: list[DslTurn] = [
    c(SW, N) | SW,
    c(S, N) | S,
    c(S, N) | S,
    h(S) | None,
    ba(SE) | None,
    wait,
    N.turn(),
    N.turn(),
    N.turn(),
]

# B2: Ax + Ti harvester + foundry + launcher
# Spawn (-1,1) => (10,26)
_B2: list[DslTurn] = [
    c(SW, E) | SW,
    c(S, N) | S,
    c(S, W) | S,
    c(S, N) | S,
    h(S) | None,
    ba(SE) | None,
    ba(SW) | None,
    c(NW, N) | NW,
    ba(SW) | None,
    h(S) | None,
    *[wait] * 16,
    f(N) | None,
    ln(NW) | None,
]

# B3: Defense -- sentinel NW of core
# Spawn (1,0) => (12,25)
_B3: list[DslTurn] = [
    NW.turn(),
    NW.rd(),
    sn(N, NE) | None,
]

register(
    KnownMap.DEFAULT_LARGE1,
    Opening(
        core_spawns=[(0, 1), (-1, 1), (1, 0)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
