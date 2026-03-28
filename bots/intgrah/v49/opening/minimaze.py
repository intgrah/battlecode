from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    2,
    23,
    """
    e c w, e; e c w, e; e c w, e; e c w, e
    e c w, e; e c w, e; e c w, e; e c w, e
    e h, x
    ne ba, x
    se ba, x
    """,
)

_B2 = parse_script(
    0,
    22,
    """
    n c s, n; n c s, n; n c s, n; n c s, n; n c s, n; n c s, n
    e c w, e; e c w, e; e c w, e
    n c s, n; n c s, n; n c s, n; n c s, n; n c s, n; n c s, n
    e c w, e; e c w, e; e c w, e
    n c s, n
    e c w, e; e c w, e; e c w, e
    s c n, s; s c n, s
    e c w, e
    e h, x
    n h, x
    ne rd, ne
    se ba, sw
    ne f, x
    x, w
    x, n
    ne rd, ne
    e br 9 9, x
    """,
)

register(
    KnownMap.MINIMAZE,
    Opening(
        core_spawns=[(1, 0), (-1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
