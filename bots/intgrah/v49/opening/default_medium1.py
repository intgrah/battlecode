from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    11,
    18,
    """
    ne rd, ne
    ne rd, ne
    ne rd, ne
    ne rd, ne
    nw sn ne, x
    w h, x
    sw ba, x
    n rd, n
    s ba, x
    """,
)

register(
    KnownMap.DEFAULT_MEDIUM1,
    Opening(
        core_spawns=[(1, -1)],
        builder_scripts=[_B1],
    ),
)
