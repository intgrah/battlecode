from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    5,
    14,
    """
    n rd, n
    n rd, n
    n rd, n
    n ba, s
    ne ba, x
    nw ba, x
    n h, s
    n c s, s
    n c s, x
    """,
)

_B2 = parse_script(
    5,
    16,
    """
    s rd, s
    s rd, s
    s rd, s
    s ba, n
    se ba, x
    sw ba, x
    s h, n
    s c n, n
    s c n, x
    """,
)

register(
    KnownMap.CORRIDORS,
    Opening(
        core_spawns=[(0, -1), (0, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
