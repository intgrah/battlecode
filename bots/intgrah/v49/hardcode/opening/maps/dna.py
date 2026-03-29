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
    rd,
    sn,
    sp,
    wait,
)

# DNA map (21x50), ROT symmetry. Core A at (10,48), occupies (9-11,47-49).
# Ti ores right (x=14-16, y=43-46), Ax ores left (x=4-7, y=43-46).
# Wall at row 45 x=6-14.
#
# IMPORTANT: Avoids building at (12,46)/(12,3) early because the core
# marker is placed there for team B. B3 builds conv at (12,46) after
# all builders have read the marker (step 8 = round 10).
#
# Spawn order: B1 (round 0), B3 (round 1), B2 (round 2).

# B1: Ti harvester. Spawn (1,-1)=(11,47).
_B1: list[DslTurn] = [
    c(NE, W) | NE,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(E) | None,
    NE.rd(),
    br(N, (-1, 2)) | N,
    NW.rd(),
    W.rd(),
    c(W, W) | W,
    c(W, W) | W,
    sp(W, W) | W,
    br(SW, (0, 3)) | None,
    c(W, S) | W,
    *[wait] * 120,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    h(W) | None,
    h(N) | E,
    E.turn(),
    f(E) | SE,
    c(E, W) | None,
]

_B2: list[DslTurn] = [
    c(NE, S) | NE,
    E.turn(),
    E.turn(),
    E.turn(),
    h(NE) | E,
    NE | h(NW),
    N | h(S),
    NW | rd(NW),
    h(W) | NW,
    *[wait] * 12,
    h(W) | None,
    *[wait] * 16,
    h(SE) | None,
    *[wait] * 5,
    br(E, (-2, 1)) | E,
    *[wait] * 6,
    sn(SE, NE) | None,
    ln(NE) | None,
    *[wait] * 18,
    h(W) | None,
    wait,
    sn(NW, N) | None,
]

_B3: list[DslTurn] = [
    NE | ln(S),
    wait,
    E | ba(S),
    wait,
    E | ba(S),
    wait,
    E | ln(S),
    wait,
    SE.rd(),
    wait,
    NE.rd(),
    wait,
    ln(N) | None,
    wait,
    ba(SW) | None,
]


register(
    KnownMap.DNA,
    Opening(
        core_spawns=[(1, -1), (0, -1), *[None] * 44, (1, -1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
