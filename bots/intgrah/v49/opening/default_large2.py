from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

# default_large2: 50x30, VER symmetry
# Core A at (3,16), Core B at (46,16)
# Closest Ti ore: (6,12) dist2=25
# Econ opening: harvester at (6,12), conveyor S, bridge to core tile (4,15)
# 3 barriers on non-output sides, launcher adjacent to bridge

_B1 = parse_script(
    4,
    15,
    """
    ne rd, ne
    ne c s, ne
    n h, x
    s br 4 15, x
    ne ba, x
    nw ba, x
    sw ln, x
    """,
)

_B2 = parse_script(
    3,
    15,
    """
    n rd, n
    ne rd, ne
    ne rd, ne
    n rd, n
    e ba, x
    """,
)

register(
    KnownMap.DEFAULT_LARGE2,
    Opening(
        core_spawns=[(1, -1), (0, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
