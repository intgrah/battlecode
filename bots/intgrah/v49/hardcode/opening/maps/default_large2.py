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
    c,
    h,
    ln,
    rd,
    wait,
)

# default_large2: 50x30, VER symmetry (E<->W reflection)
# Core A centre (3,16), occupies (2-4, 15-17). Core B at (46,16).
# Closest Ti: (6,12) Chebyshev=4, (1,24) Chebyshev=8
# Ax ores: centre of map (~20 tiles away), not viable in opening.
#
# Walls near core: cols 8-10 at rows 15-17 (##/###).
#   Row 6: cols 10-11 (##), 18-31 (##############)
#   Row 7: cols 10-12 (###), 18-35 (##################)
#   Row 8: col 9 (T=ore?), 10-11 (##), 14-16 (###), ...
#   Row 9-14: cols 10-11 (##)
#   Row 15: cols 9-10 (##), 20-21 (##), 24-25 (##)
#   Row 16: cols 8-10 (###), 20-21, 24-25
#   Row 17: cols 8-9 (##), 20-21, 24-25
#
# Strategy: two Ti harvesters with conveyor chains to core.
# B1: Ti harvester at (6,12), 4-conveyor chain to core.
# B2: Ti harvester at (1,24), 7-conveyor chain to core.
# B3: roads east from core, avoiding walls at cols 8-10.

# B1: harvester (6,12) + conveyor chain + barriers + launcher
# Spawn at offset (1,-1) = tile (4,15)
# Path: (4,15) E(5,15) N(5,14) N(5,13) E(6,13) -- all conveyors, walkable
# Chain: (6,13)W -> (5,13)S -> (5,14)S -> (5,15)W -> core(4,15)
_B1: list[DslTurn] = [
    # T1: conv(5,15) facing W, move E to (5,15)
    c(E, W) | E,
    # T2: conv(5,14) facing S, move N to (5,14)
    c(N, S) | N,
    # T3: conv(5,13) facing S, move N to (5,13)
    c(N, S) | N,
    # T4: conv(6,13) facing W, move E to (6,13)
    c(E, W) | E,
    # T5: harvester at (6,12), stay
    h(N) | None,
    # T6: barrier at (7,12), stay
    ba(NE) | None,
    # T7: barrier at (5,12), stay
    ba(NW) | None,
    # T8: road at (6,14), move S to (6,14)
    S.rd(),
    # T9: launcher at (7,13) for defense, stay
    ln(NE) | None,
    # T10: barrier at (7,14), stay
    ba(SE) | None,
    # T11: road at (6,15), move S. Row 15 col 6 = empty, OK.
    S.rd(),
    # T12: road at (6,16), move S. Row 16 col 6 = empty, OK.
    S.rd(),
    # T13: road at (6,17), move S. Row 17 col 6 = empty, OK.
    S.rd(),
    # T14: road at (7,18), move SE. Row 18 col 7 = empty, OK.
    SE.rd(),
    # T15: road at (8,19), move SE. Row 19 col 8 = empty, OK.
    SE.rd(),
    # T16: road at (9,20), move SE. Row 20 col 9 = empty, OK.
    SE.rd(),
    # T17: road at (10,21), move SE. Row 21 col 10 = empty, OK.
    SE.rd(),
    # T18: road at (11,22), move SE. Row 22 col 11 = empty, OK.
    SE.rd(),
    # T19: road at (12,23), move SE. Row 23 col 12 = empty, OK.
    SE.rd(),
    # T20: road at (13,24), move SE. Row 24 col 13 = empty, OK.
    SE.rd(),
]

# B2: harvester (1,24) + conveyor chain to core
# Spawn at offset (-1,1) = tile (2,17)
# Path: (2,17) W(1,17) S(1,18) ... S(1,23) -- all conveyors, walkable
# Chain: (1,23)N -> (1,22)N -> (1,21)N -> (1,20)N -> (1,19)N -> (1,18)N -> (1,17)E -> core(2,17)
_B2: list[DslTurn] = [
    # T2: conv(1,17) facing E, move W to (1,17)
    c(W, E) | W,
    # T3: conv(1,18) facing N, move S to (1,18)
    c(S, N) | S,
    # T4: conv(1,19) facing N, move S to (1,19)
    c(S, N) | S,
    # T5: conv(1,20) facing N, move S to (1,20)
    c(S, N) | S,
    # T6: conv(1,21) facing N, move S to (1,21)
    c(S, N) | S,
    # T7: conv(1,22) facing N, move S to (1,22)
    c(S, N) | S,
    # T8: conv(1,23) facing N, move S to (1,23)
    c(S, N) | S,
    # T9: harvester at (1,24), stay
    h(S) | None,
    # T10: barrier at (0,24) W of harvester, stay
    ba(SW) | None,
    # T11: barrier at (2,24) E of harvester, stay
    ba(SE) | None,
    # T12: road W at (0,23), move W to (0,23)
    rd(W) | W,
    # T13: launcher at (0,22) for defense
    ln(N) | None,
    # T14: return to conveyor chain
    E.turn(),
    # T15: move N to (1,22) on conveyor
    N.turn(),
    # T16: move N to (1,21) on conveyor
    N.turn(),
    # T17: move N to (1,20) on conveyor
    N.turn(),
    # T18: move N to (1,19) on conveyor
    N.turn(),
    # T19: move N to (1,18) on conveyor
    N.turn(),
    # T20: move N to (1,17) on conveyor, near core
    N.turn(),
    # T21+: wait (near core for defence)
    *[wait] * 3,
]

# B3: roads east/south from core for expansion + defense
# Spawn at offset (1,1) = tile (4,17)
# Build roads south, avoiding wall at (8,17)
_B3: list[DslTurn] = [
    # T3: road E, move to (5,17). Row 17 col 5 = empty.
    E.rd(),
    # T4: road E, move to (6,17). Row 17 col 6 = empty.
    E.rd(),
    # T5: road S, move to (6,18). Avoid col 7 row 17 -> (7,17) is `.`, but
    # (8,17) is wall. Go S first then back E.
    S.rd(),
    # T6: road S, move to (6,19).
    S.rd(),
    # T7: road SE, move to (7,20).
    SE.rd(),
    # T8: road SE, move to (8,21).
    SE.rd(),
    # T9: road SE, move to (9,22).
    SE.rd(),
    # T10: road SE, move to (10,23). Row 23 col 10 = empty.
    SE.rd(),
    # T11: SE to (11,24). Row 24 col 11 = empty.
    SE.rd(),
    # T12: SE to (12,25). Row 25 col 12 = empty.
    SE.rd(),
    # T13: SE to (13,26). Row 26 col 13 = empty.
    SE.rd(),
    # T14: Can't go SE (14,27) = wall. Go N toward (13,25).
    # Build road N, move to (13,25).
    N.rd(),
    # T15: From (13,25), continue E to (14,25). Row 25 col 14 = '.'. OK.
    E.rd(),
    # T16: continue NE to (15,24). Row 24 col 15 = '.'. OK.
    NE.rd(),
    # T17: continue NE to (16,23). Row 23 col 16 = '.'. OK (before ###).
    NE.rd(),
    # T18: continue NE to (17,22). Row 22 col 17 = '.'. OK.
    NE.rd(),
    # T19: continue E to (18,22). Row 22 col 18 = '.'. OK.
    E.rd(),
]

register(
    KnownMap.DEFAULT_LARGE2,
    Opening(
        core_spawns=[(1, -1), (-1, 1), (1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
