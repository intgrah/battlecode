from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    NW,
    SE,
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
    wait,
)

# Hourglass 27x45, HOR symmetry. Core A centre at (13,43).
# Core tiles: (12-14, 42-44).
# Ti ores at y=38 x=11..15 (dist 5 from core).
# Ax ores at y=21,23 x=12..14 (dist ~20, very far).
#
# B1: Ti harvester (13,38) + second at (15,38), conv to core.
# B2: Ti harvester (11,38), conv + bridge to core, later foundry at (12,41).
# B3: Ax conv chain x=12 north to harvester (12,23), bridge at (12,40).
# Ti leaks W from harvester(13,38) into B3's chain -> foundry gets both.
# Foundry at (12,41) outputs refined Ax S to core(12,42).

_B1: list[DslTurn] = [
    c(N, S) | N,       # conv (13,41) face S, -> (13,41)
    c(N, S) | N,       # conv (13,40) face S, -> (13,40)
    c(N, S) | N,       # conv (13,39) face S, -> (13,39)
    h(N) | None,       # harvester (13,38), stay (13,39)
    ba(NE) | None,     # barrier (14,38), stay (13,39)
    S.turn(),          # -> (13,40)
    S.turn(),          # -> (13,41)
    S.turn(),          # -> (13,42) core
    SE.turn(),         # -> (14,43) core
    rd(NE) | NE,       # road (15,42), -> (15,42)
    N.rd(),            # road (15,41), -> (15,41)
    N.rd(),            # road (15,40), -> (15,40)
    N.rd(),            # road (15,39), -> (15,39)
    h(N) | None,       # harvester (15,38), stay (15,39)
    ba(NE) | None,     # barrier (16,38), stay (15,39)
    ln(SE) | None,     # launcher (16,39), stay (15,39)
    *[wait] * 5,
]

_B2: list[DslTurn] = [
    c(NW, S) | NW,    # conv (11,41) face S, -> (11,41)
    c(N, S) | N,       # conv (11,40) face S, -> (11,40)
    c(N, S) | N,       # conv (11,39) face S, -> (11,39)
    h(N) | None,       # harvester (11,38), stay (11,39)
    ba(NW) | None,     # barrier (10,38), stay (11,39)
    S.turn(),          # -> (11,40)
    S.turn(),          # -> (11,41)
    br(S, (2, 0)) | None,  # bridge (11,42) -> core (13,42)
    ln(W) | None,      # launcher (10,41), stay (11,41)
    # Wait for income to build foundry (~15 rounds)
    *[wait] * 15,
    # Foundry at (12,41). From (11,41), E = (12,41).
    # Receives: Ti from conv chain leak, Ax from B3's bridge(12,40).
    # Outputs: S to core(12,42), W to conv(11,41) -> bridge -> core.
    f(E) | None,       # foundry (12,41), stay (11,41)
    *[wait] * 20,
]

_B3: list[DslTurn] = [
    N.turn(),          # -> (12,43) core
    N.turn(),          # -> (12,42) core
    NW.turn(),         # -> (11,41) B2's conv (built round 1)
    N.turn(),          # -> (11,40) B2's conv (built round 2)
    c(NE, S) | NE,    # conv (12,39) face S, -> (12,39)
    c(N, S) | N,       # conv (12,38) face S, -> (12,38)
    c(N, S) | N,       # conv (12,37) face S, -> (12,37)
    c(N, S) | N,       # conv (12,36) face S, -> (12,36)
    c(N, S) | N,       # conv (12,35) face S, -> (12,35)
    c(N, S) | N,       # conv (12,34) face S, -> (12,34)
    c(N, S) | N,       # conv (12,33) face S, -> (12,33)
    c(N, S) | N,       # conv (12,32) face S, -> (12,32)
    c(N, S) | N,       # conv (12,31) face S, -> (12,31)
    c(N, S) | N,       # conv (12,30) face S, -> (12,30)
    c(N, S) | N,       # conv (12,29) face S, -> (12,29)
    c(N, S) | N,       # conv (12,28) face S, -> (12,28)
    c(N, S) | N,       # conv (12,27) face S, -> (12,27)
    c(N, S) | N,       # conv (12,26) face S, -> (12,26)
    c(N, S) | N,       # conv (12,25) face S, -> (12,25)
    c(N, S) | N,       # conv (12,24) face S, -> (12,24)
    h(N) | None,       # Ax harvester (12,23), stay (12,24)
    # Walk south to place bridge
    S.turn(),          # -> (12,25)
    S.turn(),          # -> (12,26)
    S.turn(),          # -> (12,27)
    S.turn(),          # -> (12,28)
    S.turn(),          # -> (12,29)
    S.turn(),          # -> (12,30)
    S.turn(),          # -> (12,31)
    S.turn(),          # -> (12,32)
    S.turn(),          # -> (12,33)
    S.turn(),          # -> (12,34)
    S.turn(),          # -> (12,35)
    S.turn(),          # -> (12,36)
    S.turn(),          # -> (12,37)
    S.turn(),          # -> (12,38)
    S.turn(),          # -> (12,39)
    # Bridge at (12,40) targeting foundry (12,41). Vector: (0, 1).
    br(S, (0, 1)) | None,
    *[wait] * 10,
]


register(
    KnownMap.HOURGLASS,
    Opening(
        core_spawns=[(0, -1), (-1, -1), (-1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
