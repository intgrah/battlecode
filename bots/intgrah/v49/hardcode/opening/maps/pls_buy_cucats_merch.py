from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.parse import parse_script

# pls_buy_cucats_merch: 49x49 ROT, Core A at (13,17), Core B at (35,31)
#
# Ti ore at (7,21) dist=6 from core. Ax ore at (10,25) dist=8.
# Fortress walls surround core. SW exit gap: (9,18)->(8,19).
#
# Pipeline -- all Ti to foundry for max Ax production:
#   Ti harv at 7,21 -> conv 8,21 S -> 8,22 E -> 9,22 E -> 10,22 E -> foundry 11,22
#   Ax harv at 10,25 -> conv 10,24 N -> 10,23 E -> 11,23 N -> foundry 11,22
#   Foundry 11,22 -> bridge 12,22 target 12,19 -> conv 12,19 N -> core
#   Launcher at 13,22 defends bridge+foundry area

# B1: spawn offset (-1,1) = (12,18). Ti harvester + full pipeline + foundry.
_B1 = parse_script(
    12,
    18,
    """
    w rd, w
    w rd, w
    w rd, w
    sw rd, sw
    sw rd, sw
    se c s, se
    w h, x
    s c e, s
    e c e, e
    e c e, e
    se c n, se
    e rd, e
    n br 12 19, x
    ne ln, x
    x, w
    n f, x
    se ba, x
    s ba, x
    """,
)

# B2: spawn offset (0,1) = (13,18). Ax harvester + barriers.
_B2 = parse_script(
    13,
    18,
    """
    x, w
    x, w
    x, w
    x, w
    x, sw
    x, sw
    x, x
    x, se
    x, s
    x, e
    x, e
    s c e, s
    s c n, s
    s h, x
    se ba, x
    sw ba, x
    w ba, x
    """,
)

# B3: spawn offset (-1,-1) = (12,16). Conveyor inside fortress for delivery.
_B3 = parse_script(
    12,
    16,
    """
    x, s
    x, s
    s c n, x
    """,
)

register(
    KnownMap.PLS_BUY_CUCATS_MERCH,
    Opening(
        core_spawns=[(-1, 1), (0, 1), (-1, -1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
