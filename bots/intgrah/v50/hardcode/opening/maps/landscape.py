from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    DslTurn,
    E,
    N,
    S,
    W,
    c,
    h,
)

_B1: list[DslTurn] = [
    *[c(E, W) | E] * 11,
    c(S, N) | S,
    h(E) | None,
    h(S) | None,
]

_B2: list[DslTurn] = []

register(
    KnownMap.LANDSCAPE,
    Opening(
        core_spawns=[(1, 1), (1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
