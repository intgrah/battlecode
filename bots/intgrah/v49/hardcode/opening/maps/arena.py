from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    E,
    N,
    NW,
    S,
    SW,
    W,
    DslTurn,
    br,
    c,
    f,
    h,
    rd,
    wait,
)

# Arena: 25x25, ROT symmetry
# Core A at (8, 10), core tiles (7-9, 9-11)
# Ti ores: (4,8), (7,4), (12,3), (5,15)
# Ax ores: (8,13), (12,7)
#
# B1: conveyors west to Ti (4,8). Chain: (5,8)E → (6,8)E → (7,8)S → core
# B2: conveyors north to Ti (7,4). Chain: (7,5)S → (7,6)S → (7,7)S → (7,8)S → core
# B3: Ax harvester (8,13), foundry (7,13), Ti harvester (5,15), bridge to foundry

# B1 spawns at (7,9), goes west for Ti at (4,8)
_B1: list[DslTurn] = [
    c(N, S) | N,     # conveyor at (7,8) facing S, move to (7,8)
    c(W, E) | W,     # conveyor at (6,8) facing E, move to (6,8)
    c(W, E) | W,     # conveyor at (5,8) facing E, move to (5,8)
    h(W) | None,     # harvester at (4,8), stay
    # TODO: barriers around harvester, more development
]

# B2 spawns at (8,9), goes north for Ti at (7,4)
# Merges into B1's (7,8) conveyor (accepts from N, W, E — facing S)
_B2: list[DslTurn] = [
    NW.turn(),       # move NW to (7,8) [conveyor from B1, walkable]
    c(N, S) | N,     # conveyor at (7,7) facing S, move to (7,7)
    c(N, S) | N,     # conveyor at (7,6) facing S, move to (7,6)
    c(N, S) | N,     # conveyor at (7,5) facing S, move to (7,5)
    h(N) | None,     # harvester at (7,4), stay
    # TODO: barriers around harvester, more development
]

# B3 spawns at (8,11), goes south for Ax (8,13) + Ti (5,15) + foundry
_B3: list[DslTurn] = [
    S.rd(),                    # road at (8,12), move to (8,12)
    h(S) | None,               # Ax harvester at (8,13), stay at (8,12)
    *[wait] * 20,              # wait for Ti income
    f(SW) | None,              # foundry at (7,13), stay at (8,12)
    W.rd(),                    # road at (7,12), move to (7,12)
    W.rd(),                    # road at (6,12), move to (6,12)
    S.rd(),                    # road at (6,13), move to (6,13)
    S.rd(),                    # road at (6,14), move to (6,14)
    h(SW) | None,              # Ti harvester at (5,15), stay at (6,14)
    br(S, (1, -2)) | None,    # bridge at (6,15) → foundry (7,13)
    br(E, (0, -3)) | None,    # bridge at (7,14) → core (7,11)
]

register(
    KnownMap.ARENA,
    Opening(
        core_spawns=[(-1, -1), (0, -1), (0, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
