from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    2,
    2,
    """
    w c e, w; s c n, s; s c n, s; s c n, s; s c n, s; s c n, s
    se rd, se; s rd, s; w c n, w
    s br 1 7, e; s rd, s; sw c n, sw
    se h, x; s c n, x; nw ln, x; e ba, x; x, s; se ba, x
    """,
)

_B2 = parse_script(
    4,
    2,
    """
    se c w, se; e c w, e; e c w, e; e c w, e; e c w, e; e c w, e
    e c w, e; e c w, e; e c w, e; e c w, e; e c w, e
    se h, x; s c w, s; s c n, s; se h, x; s c n, x
    x, n; w f, x; sw ln, x; x, n; e ba, x; x, s; se ba, x
    """,
)

register(
    KnownMap.LANDSCAPE,
    Opening(
        core_spawns=[(-1, 0), (1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
