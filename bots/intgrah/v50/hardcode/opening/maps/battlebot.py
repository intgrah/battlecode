from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    SE,
    DslTurn,
    E,
    N,
    S,
    W,
    c,
    h,
    ln,
    sn,
    wait,
)

_B1: list[DslTurn] = [
    # Rush the Ti ore
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(SE, N) | SE,
    # Harvester first
    h(SE),
    # Sentinel
    sn(E, E),
    # Move down to grab the other one
    c(S, N) | S,
    SE.rd(),
    ln(NE),
    sn(SE, NE),
    h(S),
]

_B2: list[DslTurn] = [
    NE,
    E,
    E,
    c(E, W) | E,
    h(E),
    sn(NE, E),
    N.rd(),
    ln(NE),
]

_B3: list[DslTurn] = [
    E,
    E,
    E,
    wait,
    SE,
    S,
    c(S, N) | S,
    c(S, N) | S,
]


register(
    KnownMap.BATTLEBOT,
    Opening(
        core_spawns=[(1, 0), (1, 1), (1, 0)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
