from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.dsl import (
    NE,
    NW,
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
    sp,
    wait,
)

# DNA map (21x50), HOR symmetry. Core A at (10,48), occupies (9-11,47-49).
# Ti ores right (x=14-16, y=43-46), Ax ores left (x=4-7, y=43-46).
# Wall at row 45 x=6-14.
#
# IMPORTANT: Avoids building at (12,46)/(12,3) early because the core
# marker is placed there for team B. B3 builds conv at (12,46) after
# all builders have read the marker (step 8 = round 10).
#
# Spawn order: B1 (round 0), B3 (round 1), B2 (round 2).

# B1: Ti harvester. Spawn (1,-1)=(11,47).
# Goes E then NE to avoid marker at (12,46), builds conveyor chain.
_B1: list[DslTurn] = [
    # Turn 0 (r1): road E at (12,47), move E
    E.rd(),
    # Turn 1 (r2): conv NE at (13,46)→W, move NE to (13,46)
    c(NE, W) | NE,
    # Turn 2 (r3): conv E at (14,46)→W, move E to (14,46)
    c(E, W) | E,
    # Turn 3 (r4): conv E at (15,46)→W, move E to (15,46)
    c(E, W) | E,
    # Turn 4 (r5): harvester N at (15,45) = Ti ore. Output S to conv.
    h(N) | None,
    # Turn 5 (r6): barrier NE at (16,45) [E of harvester, on Ti ore]
    ba(NE) | None,
    # Done with core build, wait
    *[wait] * 14,
]

# B3: Infrastructure. Spawn (0,-1)=(10,47). Script index 1.
# Builds splitter, bridge, launcher, then connects (12,46), then foundry.
_B3: list[DslTurn] = [
    # Turn 0 (r2): splitter at (11,46) facing W
    sp(NE, W) | None,
    # Turn 1 (r3): conv at (10,46)→W, move N
    c(N, W) | N,
    # Turn 2 (r4): barrier at (11,45) [block splitter N output]
    ba(NE) | None,
    # Turn 3 (r5): bridge at (9,46) targeting (8,47) = foundry
    br(W, (-1, 1)) | None,
    # Turn 4 (r6): launcher at (9,45) for defense
    ln(NW) | None,
    # Turn 5 (r7): move S to (10,47) core
    S.turn(),
    # Turn 6 (r8): move E to (11,47) core
    E.turn(),
    # Turn 7 (r9): move E to (12,47) road (built by B1 turn 0)
    E.turn(),
    # Turn 8 (r10): conv N at (12,46)→W [connects B1 chain to splitter]
    # All builders have read marker by now (B2 inits r3)
    c(N, W) | None,
    # Wait for Ti income to afford foundry
    *[wait] * 14,
    # Turn 23 (r25): move W to (11,47) core
    W.turn(),
    # Turn 24 (r26): move W to (10,47) core
    W.turn(),
    # Turn 25 (r27): move W to (9,47) core
    W.turn(),
    # Turn 26 (r28): foundry at (8,47)
    f(W) | None,
    # Turn 27 (r29): conv SW at (8,48) facing E → core at (9,48)
    c(SW, E) | None,
]

# B2: Ax harvester. Spawn (-1,-1)=(9,47). Script index 2.
_B2: list[DslTurn] = [
    # Turn 0 (r3): conv at (8,46)→E, move NW to (8,46)
    c(NW, E) | NW,
    # Turn 1 (r4): conv at (7,46)→E, move W
    c(W, E) | W,
    # Turn 2 (r5): conv at (6,46)→E, move W
    c(W, E) | W,
    # Turn 3 (r6): conv at (5,46)→E, move W
    c(W, E) | W,
    # Turn 4 (r7): harvester N at (5,45) = Ax ore. Output S to conv.
    h(N) | None,
    # Turn 5 (r8): barrier NW at (4,45) [W of harvester, on Ax ore]
    ba(NW) | None,
    # Done, wait
    *[wait] * 14,
]

register(
    KnownMap.DNA,
    Opening(
        core_spawns=[(1, -1), (0, -1), (-1, -1)],
        builder_scripts=[_B1, _B3, _B2],
    ),
)
