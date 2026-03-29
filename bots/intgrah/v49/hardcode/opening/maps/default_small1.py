from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from hardcode.opening.parse import parse_script

# default_small1 (20x20) ROT symmetry
# Core A: (1,1), Core B: (18,18)
#
# Econ strategy:
# B1: Ti harv(6,1) -> conv chain -> core (Ti income)
# B2: Ti harv(3,6) -> conv chain to foundry; Ax harv(7,8) -> conv -> foundry
#     foundry -> bridge chain -> core

# B1: Ti harvester at (6,1) -> conv chain W -> core
# Spawn (1,-1) at (2,0)
_B1 = parse_script(
    2,
    0,
    """
    # Conv chain along row 0 to core
    e c w, e
    e c w, e
    e c w, e
    e c w, e
    # At (6,0). Place barriers + harv
    se ba, x
    s h, x
    sw ba, x
    # Loop around for S barrier at (6,2)
    x, w
    sw rd, sw
    se rd, se
    e ba, x
    # Harv(6,1): N=conv, S=ba, E=ba, W=ba. Output N. At (5,2).
    # Build bridge chain: bridge(3,3)->core(1,1)
    w rd, w
    w rd, w
    s br 1 1, x
    # Bridge(3,3)->core(1,1). At (3,2).
    # Launcher for defense near bridge
    sw ln, x
    # Launcher(2,3). At (3,2).
    # Now path to build second bridge (needed for foundry output chain)
    x, ne
    x, se
    s rd, s
    s br 3 3, x
    # Bridge(5,4)->bridge(3,3)->core. At (5,3).
    # Build conv(5,5) for foundry output, and bridge(4,5) for chain
    s rd, s
    sw c n, x
    # Conv(4,4)? No, (4,4) is a wall!
    """,
)

# Hmm, (4,4) is a wall. Let me simplify B1.

# Actually, let me redesign. The foundry output goes through
# conv(5,5)->W->bridge(4,5)->bridge(3,3)->core. B2 builds these.

# B1: Just Ti harv + bridge(3,3) + launcher
_B1 = parse_script(
    2,
    0,
    """
    e c w, e
    e c w, e
    e c w, e
    e c w, e
    se ba, x
    s h, x
    sw ba, x
    x, w
    sw rd, sw
    se rd, se
    e ba, x
    w rd, w
    w rd, w
    s br 1 1, x
    sw ln, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    """,
)

# B2: Full Ax pipeline
# Goes SE, builds Ax harv(7,8) with conv chain back to foundry area
# Then builds Ti harv(6,6), foundry, bridge chain
# Spawn (-1,1) at (0,2)
_B2 = parse_script(
    0,
    2,
    """
    # Path to Ax ore, using conveyors where transport is needed
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se c n, se
    se c n, se
    # At (6,8). Conv(5,7)N, conv(6,8)N.
    # Ax harvester
    e h, x
    ne ba, x
    se ba, x
    # Barrier at (8,8): go around
    n c w, n
    ne rd, ne
    se rd, se
    s ba, x
    # Harv(7,8) fully walled. At (8,7).
    # Walk back
    x, nw
    x, sw
    x, w
    x, nw
    # At (4,6). Build foundry output chain
    ne c w, x
    n br 3 3, x
    # Conv(5,5)W and bridge(4,5)->(3,3). At (4,6).
    x, ne
    # At (5,5). Ti harv(6,6) for foundry
    se h, x
    e ba, x
    # Barrier(6,5) N of harv. harv(6,6): N=ba, S=conv(6,7), E=empty, W=foundry later
    # Wait for Ti income
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    # Foundry
    s f, x
    # Foundry(5,6). Receives Ax from S(conv chain), Ti from E(harv).
    # Outputs refined Ax N -> conv(5,5)->W->bridge(4,5)->bridge(3,3)->core.
    x, x
    x, x
    x, x
    x, x
    x, x
    """,
)

register(
    KnownMap.DEFAULT_SMALL1,
    Opening(
        core_spawns=[(1, -1), (-1, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
