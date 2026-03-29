from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    6,
    7,
    """
    e c e, e
    e sn e, x
    s rd, s
    s rd, s
    s br 7 7, x
    """,
)

_B2 = parse_script(
    4,
    8,
    """
    s rd, s
    s br 7 10, x
    nw rd, nw
    w br 4 10, x
    nw rd, nw
    sw h, x
    """,
)

register(
    KnownMap.FACE,
    Opening(
        core_spawns=[(1, 0), (-1, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
