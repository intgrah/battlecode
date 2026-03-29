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
    c,
    h,
    sn,
    wait,
)

_B1: list[DslTurn] = [
    c(S, N) | S,
    h(S) | NE,
    c(NE, W) | NE,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(E) | None,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S) | None,
    wait,
    wait,
    sn(SE, S) | None,
    sn(SW, W) | None,
]

_B2: list[DslTurn] = [
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    h(W) | None,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S) | None,
    sn(SW, S) | None,
    sn(SE, E) | None,
]

register(
    KnownMap.DEFAULT_SMALL2,
    Opening(
        core_spawns=[(0, 1), (-1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
