from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.parse import parse_script

# default_large1: 40x40, ROT symmetry
# Core A at (11, 25), Core 3x3 = (10-12, 24-26)
# Ti at (8,30),(9,30),(10,30) — dist 5 south
# Ax at (9,31) — dist 6 south
#
# Econ: 3 builders (B3 is cheap — just sentinel for defense)
#
# B1 Ti delivery chain:
#   harv(10,30) -> cN(10,29) -> cN(10,28) -> cN(10,27) -> core(10,26)
#   Also: harv(10,30) W side -> B2's cN(9,30) -> foundry pipeline
#
# B2 foundry pipeline:
#   Ax harv(9,31) -> cN(9,30) -> cW(9,29) -> cN(8,29) -> foundry(8,28)
#   Ti harv(8,30) ->                          cN(8,29) -> foundry(8,28)
#   foundry(8,28) -> E -> cN(9,28) -> cE(9,27) -> cN(10,27) -> core(10,26)
#
# Barriers:
#   harv(10,30): E=barrier(11,30), S=barrier(10,31). N/W are conveyors.
#   harv(9,31):  E=barrier(10,31), W=barrier(8,31). N is conv output.
#   harv(8,30):  W=barrier(7,30),  S=barrier(8,31). N is conv output.
#
# Defense:
#   sentinel(10,22) facing NE — vision r²=32 covers NE approach
#   launcher(7,28) — adjacent to foundry

# B1: Ti harvester + conv chain to core
# Spawn (0,1) => (11,26)
# After setup, walks back to core and waits.
_B1 = parse_script(
    11,
    26,
    """
    sw c n, sw
    s c n, s
    s c n, s
    s h, x
    se ba, x
    x, n
    x, n
    x, n
    """,
)

# B2: Ax + Ti harvester + foundry + launcher
# Spawn (-1,1) => (10,26)
# Builds conv chain for foundry output (R0-R3), harvesters (R4,R9),
# barriers (R5-R8), waits 16 rounds for Ti income (R10-R25),
# then foundry (R26) and launcher (R27).
_B2 = parse_script(
    10,
    26,
    """
    sw c e, sw
    s c n, s
    s c w, s
    s c n, s
    s h, x
    se ba, x
    sw ba, x
    nw c n, nw
    sw ba, x
    s h, x
    x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x
    x, x; x, x; x, x; x, x; x, x; x, x
    n f, x
    nw ln, x
    """,
)

# B3: Defense — sentinel NW of core
# Spawn (1,0) => (12,25), east of core center
# Walks through core to NW, places road + sentinel.
_B3 = parse_script(
    12,
    25,
    """
    x, nw
    nw rd, nw
    n sn ne, x
    """,
)

register(
    KnownMap.DEFAULT_LARGE1,
    Opening(
        core_spawns=[(0, 1), (-1, 1), (1, 0)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
