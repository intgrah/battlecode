from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
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
    h,
    ln,
)

_B1: list[DslTurn] = [
    E.rd(),
    SE.rd(),
    SE.rd(),
    E.rd(),
    SE.rd(),
    S.rd(),
    SW.rd(),
    h(NW),
    ba(N),
    ba(W),
    S.rd(),
    W.rd(),
    W.rd(),
    NW.rd(),
    N.rd(),
    br(E, (-2, -2)),
    ln(N),
]

_B2: list[DslTurn] = []

register(
    KnownMap.TREE_OF_LIFE,
    Opening(
        core_spawns=[(1, -1), (-1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
