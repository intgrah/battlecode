from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    E,
    N,
    NE,
    NW,
    S,
    SW,
    W,
    DslTurn,
    c,
    f,
    h,
    rd,
    wait,
)

# Arena: 25x25, ROT symmetry
# Core A at (8, 10), core tiles (7-9, 9-11)
# Ti ores: (4,8), (7,4), (5,15)
# Ax ores: (8,13)
#
# B1: conveyors west to Ti (4,8). Chain: (5,8)E → (6,8)E → (7,8)S → core
# B2: conveyors north to Ti (7,4). Chain: (7,5)S → (7,6)S → (7,7)S → (7,8)S → core
# B3: Ax harvester (8,13), conveyor chain to foundry (7,13), Ti harvester (5,15)
#     Ti flow: (5,15)→(6,15)N→(6,14)N→(6,13)E→foundry(7,13)
#     Ax flow: harvester(8,13)→W→foundry(7,13)
#     Output:  foundry(7,13)→(7,12)N→core(7,11)

# B1 spawns at (7,9), goes west for Ti at (4,8)
_B1: list[DslTurn] = [
    c(N, S) | N,     # conveyor at (7,8) facing S, move to (7,8)
    c(W, E) | W,     # conveyor at (6,8) facing E, move to (6,8)
    c(W, E) | W,     # conveyor at (5,8) facing E, move to (5,8)
    h(W) | None,     # harvester at (4,8), stay
]

# B2 spawns at (8,9), goes north for Ti at (7,4)
# Merges into B1's (7,8) conveyor (accepts from N, W, E — facing S)
_B2: list[DslTurn] = [
    NW.turn(),       # move NW to (7,8) [conveyor from B1, walkable]
    c(N, S) | N,     # conveyor at (7,7) facing S, move to (7,7)
    c(N, S) | N,     # conveyor at (7,6) facing S, move to (7,6)
    c(N, S) | N,     # conveyor at (7,5) facing S, move to (7,5)
    h(N) | None,     # harvester at (7,4), stay
]

# B3 spawns at (8,11), goes south for Ax (8,13) + Ti (5,15) + foundry (7,13)
_B3: list[DslTurn] = [
    S.rd(),                    # road at (8,12), move to (8,12)
    h(S) | None,               # Ax harvester at (8,13), stay at (8,12)
    c(W, N) | W,               # conveyor at (7,12) facing N, move to (7,12)
    W.rd(),                    # road at (6,12), move to (6,12)
    c(S, E) | S,               # conveyor at (6,13) facing E, move to (6,13)
    c(S, N) | S,               # conveyor at (6,14) facing N, move to (6,14)
    c(S, N) | None,            # conveyor at (6,15) facing N, stay at (6,14)
    h(SW) | None,              # Ti harvester at (5,15), stay at (6,14)
    *[wait] * 25,              # wait for Ti income to afford foundry
    f(NE) | None,              # foundry at (7,13), stay at (6,14)
]

register(
    KnownMap.ARENA,
    Opening(
        core_spawns=[(-1, -1), (0, -1), (0, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
