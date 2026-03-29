from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
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
    c,
    f,
    h,
    ln,
    sn,
    wait,
)

# corridors (31x31) VER symmetry
# Core A: (5,15), Core B: (25,15)
# Walls at x=3,7,11,15,19,23,27 from y=3..27
# Core corridor: x=4-6 (between walls x=3 and x=7)
# Ti ores: (5,11), (5,19) — distance 4 from core
# Ax ores: (13,11) — distance 8, reachable via y=2 gap
# Ti in east corridor: (13,7) — used for foundry Ti input
#
# B1: Ti harv (5,11), conv→core, barrier, launcher, sentinel
# B2: Ti harv (5,19), conv→core, barrier, launcher, sentinel
# B3: Trek to x=13 corridor. Ti+Ax harvesters, foundry, bridge chain back.

# === B1: spawn (0,-1) = (5,14), goes N for Ti at (5,11) ===
_B1: list[DslTurn] = [
    c(N, S) | N,  # T0: conv(5,13)S → (5,13)
    c(N, S) | N,  # T1: conv(5,12)S → (5,12)
    h(N) | None,  # T2: harv(5,11), stay at (5,12)
    ba(NW) | None,  # T3: barrier(4,11) [W of harv]
    ln(W) | None,  # T4: launcher(4,12)
    # Sentinel: harv E output → conv(6,11)N → sentinel(6,10)
    E.turn(),  # T5: → (6,12) [road from B3, placed R4]
    c(N, N) | None,  # T6: conv(6,11)N, stay at (6,12)
    N.turn(),  # T7: → (6,11) [conv, walkable]
    sn(N, NE) | None,  # T8: sentinel(6,10) NE, stay at (6,11)
    # Move out of B3's return path
    S.turn(),  # T9: → (6,12) [road]
    W.turn(),  # T10: → (5,12) [conv]
]

# === B2: spawn (0,1) = (5,16), goes S for Ti at (5,19) ===
_B2: list[DslTurn] = [
    c(S, N) | S,  # T0: conv(5,17)N → (5,17)
    c(S, N) | S,  # T1: conv(5,18)N → (5,18)
    h(S) | None,  # T2: harv(5,19), stay at (5,18)
    ba(SW) | None,  # T3: barrier(4,19) [W of harv]
    ln(W) | None,  # T4: launcher(4,18)
    # Sentinel: harv E output → conv(6,19)N → sentinel(6,18)
    c(SE, N) | None,  # T5: conv(6,19)N, stay at (5,18)
    sn(E, SE) | None,  # T6: sentinel(6,18)SE, stay at (5,18)
]

# === B3: spawn (1,-1) = (6,14), treks to x=12-14 for Ax ===
_B3: list[DslTurn] = [
    # Phase 1: Road N from (6,14) to (6,2) — 12 steps
    N.rd(),  # T0: → (6,13)
    N.rd(),  # T1: → (6,12)
    N.rd(),  # T2: → (6,11)
    N.rd(),  # T3: → (6,10)
    N.rd(),  # T4: → (6,9)
    N.rd(),  # T5: → (6,8)
    N.rd(),  # T6: → (6,7)
    N.rd(),  # T7: → (6,6)
    N.rd(),  # T8: → (6,5)
    N.rd(),  # T9: → (6,4)
    N.rd(),  # T10: → (6,3)
    N.rd(),  # T11: → (6,2) above walls
    # Phase 2: Road E from (6,2) to (13,2)
    E.rd(),  # T12: → (7,2)
    E.rd(),  # T13: → (8,2)
    E.rd(),  # T14: → (9,2)
    E.rd(),  # T15: → (10,2)
    E.rd(),  # T16: → (11,2)
    E.rd(),  # T17: → (12,2)
    E.rd(),  # T18: → (13,2)
    # Phase 3: Road S to (13,6), Ti harv at (13,7)
    S.rd(),  # T19: → (13,3)
    S.rd(),  # T20: → (13,4)
    S.rd(),  # T21: → (13,5)
    S.rd(),  # T22: → (13,6)
    h(S) | None,  # T23: harv(13,7) [Ti], stay at (13,6)
    ba(SW) | None,  # T24: barrier(12,7) [W of Ti harv]
    # Phase 4: Detour E around Ti harv, continue S to Ax
    E.rd(),  # T25: road(14,6) → (14,6)
    S.rd(),  # T26: road(14,7) → (14,7)
    S.rd(),  # T27: road(14,8) → (14,8)
    SW.rd(),  # T28: road(13,9) → (13,9) [foundry site]
    c(N, S) | None,  # T29: conv(13,8)S [Ti→foundry], stay
    S.rd(),  # T30: road(13,10) → (13,10)
    # Wait for Ti before Ax harvester (80 Ti * ~2.5 scale ≈ 200 Ti)
    *[wait] * 10,  # T31-40: accumulate ~75 Ti income
    h(S) | None,  # T41: harv(13,11) [Ax], stay at (13,10)
    ba(SE) | None,  # T42: barrier(14,11) [E of Ax harv]
    ba(SW) | None,  # T43: barrier(12,11) [W of Ax harv]
    # Conv for Ax→foundry
    E.rd(),  # T44: road(14,10) → (14,10)
    c(W, N) | None,  # T45: conv(13,10)N [Ax→foundry], stay
    # Wait for Ti before foundry (120 Ti * ~2.9 scale ≈ 348 Ti)
    *[wait] * 60,  # T46-105
    # Build foundry
    W.turn(),  # T86: → (13,10) [conv]
    f(N) | None,  # T87: foundry(13,9)
    # Wait after foundry (+100% scale, everything expensive)
    *[wait] * 20,  # T88-107
    # Conv chain: foundry W output → (12,2)
    W.rd(),  # T108: road(12,10) → (12,10)
    c(N, N) | N,  # T109: conv(12,9)N → (12,9)
    c(N, N) | N,  # T110: conv(12,8)N → (12,8)
    c(N, N) | N,  # T111: conv(12,7)N [destroys barrier] → (12,7)
    c(N, N) | N,  # T112: conv(12,6)N → (12,6)
    c(N, N) | N,  # T113: conv(12,5)N → (12,5)
    c(N, N) | N,  # T114: conv(12,4)N → (12,4)
    c(N, N) | N,  # T115: conv(12,3)N → (12,3)
    # Bridge (12,2) → (9,2)
    br(N, (-3, 0)) | None,  # T116
    # Wait before 2nd bridge
    *[wait] * 10,  # T117-126
    # Walk W to (9,2)
    NW.turn(),  # T127: → (11,2)
    W.turn(),  # T128: → (10,2)
    W.turn(),  # T129: → (9,2)
    S.rd(),  # T130: road(9,3) → (9,3)
    # Bridge (9,2) → (6,2)
    br(N, (-3, 0)) | None,  # T131
    # Walk W to (6,2)
    NW.turn(),  # T132: → (8,2)
    W.turn(),  # T133: → (7,2)
    W.turn(),  # T134: → (6,2)
    # Conv chain S: (6,2) to (6,14) core
    N.rd(),  # T135: road(6,1) → (6,1)
    c(S, S) | S,  # T136: conv(6,2)S → (6,2)
    c(S, S) | S,  # T137: conv(6,3)S → (6,3)
    c(S, S) | S,  # T138: conv(6,4)S → (6,4)
    c(S, S) | S,  # T139: conv(6,5)S → (6,5)
    c(S, S) | S,  # T140: conv(6,6)S → (6,6)
    c(S, S) | S,  # T141: conv(6,7)S → (6,7)
    c(S, S) | S,  # T142: conv(6,8)S → (6,8)
    c(S, S) | S,  # T143: conv(6,9)S → (6,9)
    c(S, S) | S,  # T144: conv(6,10)S → (6,10) [destroys sentinel]
    c(S, S) | S,  # T145: conv(6,11)S → (6,11) [destroys conv N]
    c(S, S) | S,  # T146: conv(6,12)S → (6,12)
    c(S, S) | S,  # T147: conv(6,13)S → (6,13)
    # conv(6,13)S → (6,14) core. Refined Ax delivered!
]

register(
    KnownMap.CORRIDORS,
    Opening(
        core_spawns=[(0, -1), (0, 1), (1, -1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
