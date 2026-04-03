from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    SE,
    DslTurn,
    E,
    S,
    W,
    br,
    c,
    h,
)

_B1: list[DslTurn] = [
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    c(E, W) | E,
    NE.rd(),
    br(E, (-2, 1)) | E,
    c(E, W) | E,
    c(E, W) | E,
    h(S) | None,
    E.rd(),
    NE.rd(),
    br(SE, (-3, 0)) | SE,
    c(E, W) | E,
    h(S) | None,
]


register(
    KnownMap.WASTELAND,
    Opening(
        core_spawns=[(1, 0)],
        builder_scripts=[_B1],
    ),
)
