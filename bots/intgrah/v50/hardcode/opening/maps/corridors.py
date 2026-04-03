from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    NW,
    SE,
    SW,
    DslTurn,
    N,
    S,
    br,
    c,
    h,
    sn,
)

# Corridors: 31x31, VER symmetry (E↔W)
# Core A at (5, 15), core tiles (4-6, 14-16)
# Wall columns at x=3,7 from y=3-27 bound the core corridor (x=4-6)
#
# Flow (north half):
#   harv(5,7)→(5,8)S→(5,9)S→bridge(5,10)→(5,12)S→(5,13)S→core
#   harv(5,11)→S(5,12) + N→bridge(5,10)→(5,12)→core
#   harv(5,7)→N→sentinel(5,6) [ammo]
#
# Flow (south half, symmetric):
#   harv(5,23)→(5,22)N→(5,21)N→bridge(5,20)→(5,18)N→(5,17)N→core
#   harv(5,19)→N(5,18) + S→bridge(5,20)→(5,18)→core
#   harv(5,23)→S→sentinel(5,24) [ammo]

# B1 spawns at (5,14), goes north
_B1: list[DslTurn] = [
    c(N, S) | N,  # 0: conv (5,13)S, move to (5,13)
    c(N, S) | N,  # 1: conv (5,12)S, move to (5,12)
    h(N),  # 2: harvester (5,11)
    NW.rd(),  # 3: road (4,11), move to (4,11) [sidestep W]
    br(NE, (0, 2)) | NE,  # 4: bridge (5,10)→(5,12), walk onto bridge
    c(N, S) | N,  # 5: conv (5,9)S, move to (5,9)
    c(N, S) | N,  # 6: conv (5,8)S, move to (5,8)
    h(N),  # 7: harvester (5,7)
    NW.rd(),  # 8: road (4,7), move to (4,7) [sidestep]
    sn(NE, N),  # 9: sentinel (5,6)N [guards north entry]
]

# B2 spawns at (5,16), goes south (symmetric)
_B2: list[DslTurn] = [
    c(S, N) | S,  # 0: conv (5,17)N, move to (5,17)
    c(S, N) | S,  # 1: conv (5,18)N, move to (5,18)
    h(S),  # 2: harvester (5,19)
    SW.rd(),  # 3: road (4,19), move to (4,19) [sidestep W]
    br(SE, (0, -2)) | SE,  # 4: bridge (5,20)→(5,18), walk onto bridge
    c(S, N) | S,  # 5: conv (5,21)N, move to (5,21)
    c(S, N) | S,  # 6: conv (5,22)N, move to (5,22)
    h(S),  # 7: harvester (5,23)
    SW.rd(),  # 8: road (4,23), move to (4,23) [sidestep]
    sn(SE, S),  # 9: sentinel (5,24)S [guards south entry]
]

register(
    KnownMap.CORRIDORS,
    Opening(
        core_spawns=[(0, -1), (0, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
