from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    5,
    34,
    """
    e c w, e
    e rd, e
    se h, x
    s br 9 33, x
    sw ln, x
    x, n
    e c w, x
    se c n, x
    w c s, x
    x, n
    x, ne
    s rd, s
    e ln, x
    se f, x
    x, s
    se ba, x
    x, n
    x, ne
    se rd, se
    s rd, s
    s rd, s
    sw ba, x
    s rd, s
    s rd, s
    w rd, w
    w ba, x
    """,
)

_B2 = parse_script(
    5,
    35,
    """
    x, ne
    ne c w, ne
    n rd, n
    ne rd, ne
    e rd, e
    ne rd, ne
    ne rd, ne
    e rd, e
    se rd, se
    s br 11 31, x
    se c w, se
    e h, x
    n rd, n
    e ba, s
    s rd, s
    e ba, x
    se rd, se
    ne rd, ne
    n ba, x
    x, sw
    x, nw
    x, n
    x, nw
    sw ln, x
    w rd, w
    sw br 9 33, x
    """,
)

register(
    KnownMap.GALAXY,
    Opening(
        core_spawns=[(1, -1), (1, 0)],
        builder_scripts=[_B1, _B2],
    ),
)
