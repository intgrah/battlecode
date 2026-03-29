from hardcode.known import KnownMap
from hardcode.opening import Opening, register
from hardcode.opening.parse import parse_script

# tree_of_life: 39x30, VER symmetry (E<->W reflection)
# Core A at (4,22), Core B at (34,22)
#
# Key ores for team A:
#   Ti (8,25) manhattan=7  -- closest, SE of core
#   Ti (4,4) manhattan=18  -- on route to Ax
#   Ax (6,2) manhattan=22  -- far north behind walls
#
# Strategy: econ.
#   B1: Ti harvester at (8,25), bridge to core, barriers, launcher.
#   B2: Road north to Ax(6,2)/Ti(4,4), foundry at (4,2),
#       conveyor chain south along x=3 to deliver refined Ax to core.
#
# Resource flow:
#   Ti harv(4,4) N-> conv(4,3) N-> foundry(4,2)
#   Ax harv(6,2) S-> conv(6,3) W-> conv(5,3) W-> conv(4,3) N-> foundry(4,2)
#   Foundry(4,2) W-> conv(3,2) S-> conv(3,3) S-> ... -> conv(3,20) S-> core(3,21)

# ── B1: Ti harvester at (8,25) ──────────────────────────────
# Spawn offset (1,-1) -> pos (5,21).
# Route through row-23/24 wall gap.
# Harvester output W -> bridge(7,25) -> (5,23)=core.
_B1 = parse_script(
    5,
    21,
    """
    # T1-T7: road to (9,26) via gap
    e rd, e
    se rd, se
    se rd, se
    e rd, e
    se rd, se
    s rd, s
    sw rd, sw
    # T8: harvester at (8,25)
    nw h, x
    # T9-T10: barriers (E and S of harvester, N is wall)
    n ba, x
    w ba, x
    # T11-T15: road south and west to (6,25)
    s rd, s
    w rd, w
    w rd, w
    nw rd, nw
    n rd, n
    # T16: bridge at (7,25) -> core(5,23), vec=(-2,-2) dist2=8
    e br -2 -2, x
    # T17: launcher adjacent to bridge at (6,24)
    n ln, x
    """,
)

# ── B2: Ax pipeline ─────────────────────────────────────────
# Spawn offset (-1,-1) -> pos (3,21).
# Phase 1: Road north along west corridor (T2-T19).
# Phase 2: Harvesters + foundry (T20-T38, with income waits).
# Phase 3: Conveyor chain x=3 from (3,2) to (3,20) (T39-T58).
_B2 = parse_script(
    3,
    21,
    """
    # Phase 1: road north (T2-T19)
    nw rd, nw
    nw rd, nw
    n rd, n
    nw rd, nw
    n rd, n
    n rd, n
    n rd, n
    n rd, n
    n rd, n
    n rd, n
    n rd, n
    n rd, n
    n rd, n
    ne rd, ne
    ne rd, ne
    n rd, n
    ne rd, ne
    # T19: conv(4,3) facing N for foundry Ti input
    ne c n, ne
    # T20: conv(5,3) facing W for Ax transport
    e c w, e
    # Phase 2: harvesters + foundry (T21-T38)
    # T21: Ax harvester at (6,2)
    ne h, x
    # T22: barrier W of Ax harv at (5,2)
    n ba, x
    # T23: conv(6,3) facing W for Ax output path
    e c w, e
    # T24: barrier E of Ax harv at (7,2)
    ne ba, x
    # T25-T26: walk back to (4,3)
    x, w
    x, w
    # T27: Ti harvester at (4,4)
    s h, x
    # T28: barrier E of Ti harv at (5,4)
    se ba, x
    # T29-T38: wait for Ti income to afford foundry (~240 Ti)
    x, x; x, x; x, x; x, x; x, x
    x, x; x, x; x, x; x, x; x, x
    # T39: foundry at (4,2)
    n f, x
    # T40: launcher W of foundry at (3,3)
    # (will be destroyed later by conv chain, but protects early)
    # Actually place launcher at (3,1) NW of foundry
    nw ln, x
    # Phase 3: conv chain x=3 from (3,2) to (3,20) (T41-T60)
    # T41: conv(3,2) facing S (receives foundry output)
    nw c s, x
    # T42: conv(3,3) facing S + move there
    w c s, w
    # T43-T59: conv(3,4) to conv(3,20), each facing S
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    s c s, s
    """,
)


register(
    KnownMap.TREE_OF_LIFE,
    Opening(
        core_spawns=[(1, -1), (-1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
