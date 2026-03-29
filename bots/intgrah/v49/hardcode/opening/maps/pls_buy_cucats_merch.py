from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
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

# pls_buy_cucats_merch: 49x49 ROT, Core A at (13,17), Core B at (35,31)

# B1: spawn offset (-1,1) = (12,18). Ti harvester + full pipeline + foundry.
_B1: list[DslTurn] = [
    W.rd(),
    W.rd(),
    W.rd(),
    SW.rd(),
    SW.rd(),
    c(SE, S) | SE,
    h(W) | None,
    c(S, E) | S,
    c(E, E) | E,
    c(E, E) | E,
    c(SE, N) | SE,
    E.rd(),
    # bridge at N=(12,22), target (12,19), vec=(0,-3)
    br(N, (0, -3)) | None,
    ln(NE) | None,
    W.turn(),
    f(N) | None,
    ba(SE) | None,
    ba(S) | None,
]

# B2: spawn offset (0,1) = (13,18). Ax harvester + barriers.
_B2: list[DslTurn] = [
    W.turn(),
    W.turn(),
    W.turn(),
    W.turn(),
    SW.turn(),
    SW.turn(),
    wait,
    SE.turn(),
    S.turn(),
    E.turn(),
    E.turn(),
    c(S, E) | S,
    c(S, N) | S,
    h(S) | None,
    ba(SE) | None,
    ba(SW) | None,
    ba(W) | None,
]

# B3: spawn offset (-1,-1) = (12,16). Conveyor inside fortress for delivery.
_B3: list[DslTurn] = [
    S.turn(),
    S.turn(),
    c(S, N) | None,
]

register(
    KnownMap.PLS_BUY_CUCATS_MERCH,
    Opening(
        core_spawns=[(-1, 1), (0, 1), (-1, -1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
