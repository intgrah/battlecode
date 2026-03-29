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
    rd,
    sn,
    sp,
    wait,
)

# default_small2 (21x21) HOR symmetry (N<->S)
# Core A: (10,1). Ti: (10,4)d=3. Ax: (9,9)d=8.
# Diamond wall rows 3-8, wall at row 6 cols 7-13.
# West gap: col 4-5 area.
#
# B1: splitter(10,3)N + Ti harv(10,4). Splitter sends Ti to core AND foundry.
#     Conv(9,3)W -> foundry(8,3). Conv(8,4)N for Ax pipeline.
#     Conv(8,2)E for refined Ax -> core. Sentinel + launcher.
# B2: Walk west around wall to Ax harv(9,9).
#     Conv(9,8)W -> conv(8,8)N -> bridge(8,7)->(8,4) -> conv(8,4)N -> foundry.
#     Dedicated Ax path (no Ti harv on same pipeline).
# Foundry(8,3) built last by B1 after income.
#
# Ti flow: harv(10,4) -> splitter(10,3)N -> core(10,2) AND conv(9,3)W
#          -> foundry(8,3)
# Ax flow: harv(9,9) -> N -> conv(9,8)W -> conv(8,8)N -> bridge(8,7)
#          -> conv(8,4)N -> foundry(8,3)
# Refined Ax: foundry(8,3) -> N -> conv(8,2)E -> core(9,2)

_B1: list[DslTurn] = [
    # T1: splitter(10,3) facing N, move S to (10,3)
    sp(S, N) | S,
    # T2: harv(10,4) [Ti], stay at (10,3)
    h(S) | None,
    # T3: road(11,3), move E to (11,3)
    E.rd(),
    # T4: barrier(11,4) [E of Ti harv], move W to (10,3)
    ba(S) | W,
    # T5: conv(9,3) facing W [Ti to foundry], move W to (9,3)
    c(W, W) | W,
    # T6: barrier(9,4) [W of Ti harv], stay at (9,3)
    ba(S) | None,
    # T7: conv(8,4) facing N [Ax pipeline to foundry], move SW to (8,4)
    c(SW, N) | SW,
    # T8: road(9,5), move SE to (9,5)
    rd(SE) | SE,
    # T9: barrier(10,5) [S of Ti harv], stay at (9,5)
    ba(E) | None,
    # T10: launcher(8,5) for defense, stay
    ln(W) | None,
    # T11: move NW to (8,4) [conveyor]
    NW.turn(),
    # T12: move NE to (9,3) [conveyor]
    NE.turn(),
    # T13: move E to (10,3) [splitter]
    E.turn(),
    # T14: move E to (11,3) [road]
    E.turn(),
    # T15: sentinel(12,3) facing S, stay at (11,3)
    sn(E, S) | None,
    # Wait for income from Ti harv
    *[wait] * 2,
    # T21: move W to (10,3) [splitter]
    W.turn(),
    # T22: move W to (9,3) [conveyor]
    W.turn(),
    # T23: conv(8,2) facing E [refined Ax -> core], stay at (9,3)
    c(NW, E) | None,
    # T24: foundry(8,3) immediately, stay at (9,3)
    f(W) | None,
    # Continue waiting - fall through to regular policy eventually
    *[wait] * 20,
]

_B2: list[DslTurn] = [
    # Phase 1: Walk west from (9,0) around wall [10 steps]
    rd(W) | W,  # T1: road(8,0), to (8,0)
    rd(W) | W,  # T2: road(7,0), to (7,0)
    rd(SW) | SW,  # T3: road(6,1), to (6,1)
    rd(SW) | SW,  # T4: road(5,2), to (5,2)
    rd(SW) | SW,  # T5: road(4,3), to (4,3)
    rd(S) | S,  # T6: road(4,4), to (4,4)
    rd(S) | S,  # T7: road(4,5), to (4,5)
    rd(S) | S,  # T8: road(4,6), to (4,6)
    rd(SE) | SE,  # T9: road(5,7), to (5,7)
    rd(SE) | SE,  # T10: road(6,8), to (6,8)
    # Phase 2: Continue to Ax area via south route
    rd(S) | S,  # T11: road(6,9), to (6,9)
    rd(S) | S,  # T12: road(6,10), to (6,10)
    rd(SE) | SE,  # T13: road(7,11), to (7,11)
    rd(E) | E,  # T14: road(8,11), to (8,11)
    rd(E) | E,  # T15: road(9,11), to (9,11)
    rd(N) | N,  # T16: road(9,10), to (9,10)
    # Phase 3: Ax harvester at (9,9) + barriers
    h(N) | None,  # T17: harv(9,9)[Ax], stay at (9,10)
    ba(NE) | None,  # T18: barrier(10,9)[E of harv], stay
    ba(NW) | None,  # T19: barrier(8,9)[W of harv], stay
    # Phase 4: Walk back to build Ax pipeline
    S.turn(),  # T20: to (9,11)[road]
    W.turn(),  # T21: to (8,11)[road]
    W.turn(),  # T22: to (7,11)[road]
    NW.turn(),  # T23: to (6,10)[road]
    N.turn(),  # T24: to (6,9)[road]
    N.turn(),  # T25: to (6,8)[road]
    # Phase 5: Build Ax pipeline
    rd(SE) | SE,  # T26: road(7,9), to (7,9)
    c(NE, N) | NE,  # T27: conv(8,8)N, to (8,8) [on conveyor]
    br(N, (0, -3)) | None,  # T28: bridge(8,7) target (8,4)[conv], stay
    c(E, W) | None,  # T29: conv(9,8)W [Ax harv output], stay at (8,8)
    # Phase 6: Defense
    SW.turn(),  # T30: to (7,9)[road]
    ln(S) | None,  # T31: launcher(7,10), stay at (7,9)
    # Phase 7: Additional barriers for protection
    NW.turn(),  # T32: to (6,8)[road]
    ba(N) | None,  # T33: barrier(6,7), stay at (6,8)
    ba(SW) | None,  # T34: barrier(5,9)? SW of (6,8) is (5,9). ✓
    # Wait for income and fall through
    *[wait] * 15,
]

register(
    KnownMap.DEFAULT_SMALL2,
    Opening(
        core_spawns=[(0, 1), (-1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
