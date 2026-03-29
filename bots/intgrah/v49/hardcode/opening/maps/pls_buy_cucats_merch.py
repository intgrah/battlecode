from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    DslTurn,
)

_B1: list[DslTurn] = []

_B2: list[DslTurn] = []

_B3: list[DslTurn] = []

register(
    KnownMap.PLS_BUY_CUCATS_MERCH,
    Opening(
        core_spawns=[(-1, 1), (0, 1), (-1, -1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
