from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    12,
    18,
    """
    sw rd, sw
    nw rd, nw
    w rd, w
    sw rd, sw
    s rd, s
    s rd, s
    s rd, s
    w rd, w
    x c e, x
    e br 10 22, x
    n h, x
    ne ba, x
    nw ba, x
    """,
)

_B2 = parse_script(
    14,
    18,
    """
    x, w
    x, w
    x, sw
    x, nw
    x, w
    x, sw
    x, s
    x, s
    x, s
    se rd, se
    se c n, se
    s h, x
    se ba, x
    sw ba, x
    n rd, n
    n c s, x
    e br 11 20, x
    se rd, se
    ne ln, x
    x, nw
    x, w
    n ln, x
    e f, x
    """,
)

_B3 = parse_script(
    12,
    16,
    """
    x, s
    x, s
    w c e, x
    sw c n, x
    x, sw
    s c n, x
    """,
)

register(
    KnownMap.PLS_BUY_CUCATS_MERCH,
    Opening(
        core_spawns=[(-1, 1), (1, 1), (-1, -1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
