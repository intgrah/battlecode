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
    wait,
)

# galaxy (40x40), ROT symmetry
# Core A: (4, 35), Core B: (35, 4)
# Ti: (8,35) dist=4, (6,29) dist=6
# Ax: (15,31) dist=11
#
# Econ opening with full foundry pipeline.
# B2 (turn 1): walks NE to Ax (15,31) via conveyors along row 31.
# B1 (turn 2): Ti harvester (8,35) bridges to core; Ti (6,29) bridges to foundry.
# Foundry at (5,31); refined Ax bridges to core (4,34).

# -------------------------------------------------------------------
# B2: Ax harvester at (15,31), conveyor chain W along row 31
# Spawn (0,-1) at (4,34)
# -------------------------------------------------------------------
_B2: list[DslTurn] = [
    # Walk NE to row 31 via diagonal roads
    NE.rd(),  # T1: road (5,33), move to (5,33)
    NE.rd(),  # T2: road (6,32), move to (6,32)
    E.rd(),  # T3: road (7,32), move to (7,32)
    # Conveyor chain along row 31 facing W (walkable)
    c(NE, W) | NE,  # T4: conv (8,31), move to (8,31)
    c(E, W) | E,  # T5: conv (9,31)
    c(E, W) | E,  # T6: conv (10,31)
    c(E, W) | E,  # T7: conv (11,31)
    c(E, W) | E,  # T8: conv (12,31)
    c(E, W) | E,  # T9: conv (13,31)
    c(E, W) | E,  # T10: conv (14,31), at (14,31)
    # Ax harvester + barriers
    h(E) | None,  # T11: harvester (15,31), stay at (14,31)
    ba(NE) | None,  # T12: barrier (15,30) -- N of harvester
    ba(SE) | None,  # T13: barrier (15,32) -- S of harvester
    # Walk back to place barriers protecting infrastructure
    W.turn(),  # T14: (13,31)
    ba(S) | None,  # T15: barrier (13,32) -- protect conv
    W.turn(),  # T16: (12,31)
    W.turn(),  # T17: (11,31)
    ba(S) | None,  # T18: barrier (11,32) -- protect conv
    W.turn(),  # T19: (10,31)
    W.turn(),  # T20: (9,31)
    ba(S) | None,  # T21: barrier (9,32) -- protect conv
    W.turn(),  # T22: (8,31)
    SW.turn(),  # T23: (7,32) -- road from T3
    # Barriers near bridge (7,31) and conv chain entry
    ba(E) | None,  # T24: barrier (8,32) -- shield conv entry
    ba(SE) | None,  # T25: barrier (8,33) -- shield from SE
    ba(SW) | None,  # T26: barrier (6,33) -- shield from SW
    # Wait
    *[wait] * 10,
]

# -------------------------------------------------------------------
# B1: Ti harvesters + foundry pipeline
# Spawn (1,-1) at (5,34)
# -------------------------------------------------------------------
_B1: list[DslTurn] = [
    # --- Ti harvester at (8,35) → bridge → core ---
    E.rd(),  # T1: road (6,34), move to (6,34)
    br(SE, (-2, 0)) | None,  # T2: bridge (7,35) → core (5,35), stay
    E.rd(),  # T3: road (7,34), move to (7,34)
    h(SE) | None,  # T4: harvester (8,35), stay
    ln(SW) | None,  # T5: launcher (6,35) -- defends bridge (7,35)
    # --- Head N toward foundry area ---
    N.rd(),  # T6: road (7,33), move to (7,33)
    N.turn(),  # T7: move to (7,32) -- road from B2
    # Bridge: Ax conv chain → foundry (5,31)
    br(N, (-2, 0)) | None,  # T8: bridge (7,31) → (5,31), stay at (7,32)
    # --- Continue NW to Ti (6,29) ---
    NW.rd(),  # T9: road (6,31), move to (6,31)
    NW.rd(),  # T10: road (5,30), move to (5,30)
    # Bridge: Ti from 2nd harvester → foundry
    br(N, (0, 2)) | None,  # T11: bridge (5,29) → (5,31), stay
    # Second Ti harvester
    h(NE) | None,  # T12: harvester (6,29), stay at (5,30)
    # Bridge: foundry output → core
    br(SW, (0, 3)) | None,  # T13: bridge (4,31) → core (4,34), stay
    # Wait for Ti income, then build foundry
    *[wait] * 6,
    # Foundry at (5,31) -- built LAST (100% scaling)
    f(S) | None,  # foundry (5,31) = S of (5,30)
    # Place barriers to protect foundry area
    ba(E) | None,  # barrier (6,30) -- protect bridge (5,29) area
    ba(NW) | None,  # barrier (4,29) -- protect bridge area
    ba(W) | None,  # barrier (4,30) -- protect foundry from W
    # Wait
    *[wait] * 12,
]

register(
    KnownMap.GALAXY,
    Opening(
        core_spawns=[(0, -1), (1, -1)],
        builder_scripts=[_B2, _B1],
    ),
)
