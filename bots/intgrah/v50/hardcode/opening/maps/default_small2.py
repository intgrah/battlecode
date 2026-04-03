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
    h(E),
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S),
    wait,
    wait,
    sn(SE, S),
    sn(SW, W),
]

_B2: list[DslTurn] = [
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    c(W, E) | W,
    h(W),
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    c(S, N) | S,
    h(S),
    sn(SW, S),
    sn(SE, E),
]

register(
    KnownMap.DEFAULT_SMALL2,
    Opening(
        core_spawns=[(0, 1), (-1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
