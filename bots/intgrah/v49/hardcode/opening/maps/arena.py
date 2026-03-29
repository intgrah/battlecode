from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    7,
    9,
    """sw rd, sw; nw rd, nw; nw h, x; n br 7 9, x
    x, n; ne rd, ne; ne rd, ne; n rd, n; n h, s
    n c s, n; s br 5 8, x; ne rd, ne; ne rd, ne
    e rd, e; e rd, e
    x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x; x, x
    e h, x; se rd, se; ne ba, nw; se ba, w
    e br 9 3, x
    w br 7 5, x; se ln, w; x, sw; x, sw; se ln, s
    x, sw; x, sw;
    se ln, s
    """,
)

_B2 = parse_script(
    7,
    11,
    """sw sp e, sw; s br 7 11, s; s rd, s; sw h, x
        w br 6 12, w; e ln 8 12, x; sw ba, x; se rd, se; sw ba, nw; se ba, x
        """,
)


_B3 = parse_script(
    8,
    11,
    """s rd, s; e ba, x; se ba, x; s ba, x; sw ba, x; w gn e, ne

        """,
)

register(
    KnownMap.ARENA,
    Opening(
        core_spawns=[(-1, -1), (-1, 1), (0, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
