from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    11,
    47,
    """
    ne c w, ne
    e c w, e
    e c w, e
    e c w, e
    e h, x
    ne ba, x
    s rd, s
    e ba, x
    """,
)

_B2 = parse_script(
    10,
    47,
    """
    ne c w, ne
    w c w, w
    w c w, w
    x, s
    sw c e, x
    x, sw
    nw ln, x
    x, x; x, x; x, x; x, x; x, x
    n f, x
    """,
)

_B3 = parse_script(
    9,
    47,
    """
    nw c s, nw
    w c e, w
    w c e, w
    w c e, w
    w h, x
    nw ba, x
    sw ba, x
    """,
)

_NONES: list[tuple[int, int] | None] = [None] * 15

register(
    KnownMap.DNA,
    Opening(
        core_spawns=[(1, -1), (0, -1), (-1, -1), *_NONES],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
