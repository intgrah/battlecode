from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    E,
    N,
    NE,
    NW,
    S,
    SE,
    SW,
    W,
    DslTurn,
    ba,
    c,
    f,
    gn,
    h,
    ln,
    sn,
    sp,
    wait,
)

# Arena: 25x25, ROT symmetry
# Core A at (8, 10), core tiles (7-9, 9-11)
#
# B1 (9t): NW to (6,8), west to Ti(4,8), 3 barriers, launcher(6,6)
# B2 (11t): conv chain (7,8)S→(7,5)S, harvester(7,4), 3 barriers on
#           harvester (7,3)(8,4)(6,4), east blockade (8,5)(8,6)
# B3: sentinel(8,12)SE east of splitter, defense before foundry
#   Ti: (5,15)→(6,15)N→(6,14)N→(6,13)E→foundry(7,13)
#   Ax: (8,13)→W→foundry(7,13)
#   Out: foundry→splitter(7,12)N→core(7,11) + sentinel(8,12)

_B1: list[DslTurn] = [
    c(NW, E) | NW,        # 0: conv (6,8)E, move to (6,8)
    c(W, E) | W,           # 1: conv (5,8)E, move to (5,8)
    ba(SW) | None,         # 2: barrier (4,9)
    h(W) | None,           # 3: harvester (4,8)
    NW.rd(),               # 4: road (4,7), move to (4,7)
    ba(SW) | None,         # 5: barrier (3,8)
    SE | ba(NW),           # 6: move to (5,8), barrier (4,7) [replaces road]
    N.rd(),                # 7: road (5,7), move to (5,7)
    ln(NE) | None,         # 8: launcher (6,6)
]

_B2: list[DslTurn] = [
    c(NW, S) | NW,        # 0:  conv (7,8)S, move to (7,8)
    c(N, S) | N,           # 1:  conv (7,7)S, move to (7,7)
    c(N, S) | N,           # 2:  conv (7,6)S, move to (7,6)
    c(N, S) | N,           # 3:  conv (7,5)S, move to (7,5)
    h(N) | None,           # 4:  harvester (7,4)
    NW.rd(),               # 5:  road (6,4), move to (6,4)
    ba(NE) | SE,           # 6:  barrier (7,3), move back to (7,5)
    ba(NW) | None,         # 7:  barrier (6,4) [replaces road]
    ba(NE) | None,         # 8:  barrier (8,4)
    ba(E) | None,          # 9:  barrier (8,5)
    ba(SE) | None,         # 10: barrier (8,6)
]

# Build order: harvesters + sentinel → defense → long wait → foundry LAST.
# Sentinel at (8,12) = east of splitter, receives refined Ax from east output.
_B3: list[DslTurn] = [
    # --- Phase 1: infrastructure + income ---
    S.rd(),                # 0:  road (7,12), move to (7,12)
    h(SE) | None,          # 1:  Ax harvester (8,13)
    sn(E, SE) | None,      # 2:  sentinel (8,12)SE — east of splitter
    W.rd(),                # 3:  road (6,12), move to (6,12)
    c(S, E) | S,           # 4:  conv (6,13)E, move to (6,13)
    c(S, N) | S,           # 5:  conv (6,14)N, move to (6,14)
    c(S, N) | None,        # 6:  conv (6,15)N
    h(SW) | None,          # 7:  Ti harvester (5,15)
    # --- Phase 2: defense (before foundry to keep scale manageable) ---
    ba(W) | None,          # 8:  barrier (5,14)
    N | sp(NE, N),         # 9:  move to (6,13), splitter (7,12)N [replaces road]
    ln(W) | S,             # 10: launcher (5,13), move to (6,14)
    wait,                  # 11: wait 1 round for gunner affordability
    gn(E, E) | S,          # 12: gunner (7,14)E, move to (6,15)
    ba(SW) | N,            # 13: barrier (5,16), move to (6,14)
    # --- Phase 3: accumulate Ti for foundry ---
    *[wait] * 63,          # 14-76: wait for income (~5 Ti/round)
    f(NE) | None,          # 77: foundry (7,13) — LAST build
]

register(
    KnownMap.ARENA,
    Opening(
        core_spawns=[(-1, -1), (0, -1), (-1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
