from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    3,
    26,
    """
    ne rd, ne; ne rd, ne; ne rd, ne; n rd, n
    ne rd, ne; ne rd, ne; ne rd, ne; ne rd, ne
    s rd, s; e h, x; ne br 9 16, x; x, x
    x c n, x; n c w, x; x, n; n rd, n
    nw br 6 16, x; x c w, s; w c n, x; nw f, x
    ne rd, ne; se rd, se; ne rd, ne
    n h, sw; ne br 10 17, x
    """,
)

_B2 = parse_script(
    1,
    26,
    """
    ne rd, ne; ne c s, ne; n c s, x; s br 1 26, n
    ne rd, ne; ne rd, ne; ne rd, ne; n rd, n; n rd, n; n rd, n; n rd, n
    x c s, x; s c s, s; s c s, s; s c s, s; s c s, s; s c s, s; s c s, s
    s br 3 23, x
    """,
)

register(
    KnownMap.CINNAMON_ROLL,
    Opening(
        core_spawns=[(1, -1), (-1, -1)] + [None] * 28,
        builder_scripts=[_B1, _B2],
    ),
)
