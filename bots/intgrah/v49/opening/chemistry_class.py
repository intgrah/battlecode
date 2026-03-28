from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    13,
    22,
    """
    n sp s, n
    n c s, n
    n c s, n
    w c e, w
    nw rd, nw
    nw br 12 19, x
    w h, x
    n h, nw
    w h, x

    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x

    n h, x
    ne sn ne, x
    nw rd, nw
    n rd, n
    n rd, n
    nw rd, nw
    nw br 7 9, nw
    ne rd, ne
    n rd, n
    nw c e, nw
    ne rd, ne
    e rd, e
    ne br 8 9, x
    sw f, ne
    w h, x
    n h, x
    e h, x



    """,
)

_B2 = parse_script(
    15,
    22,
    """
    x, nw
    """,
)

_B3 = parse_script(
    13,
    24,
    """
    s sp n, s
    s c n, s
    s c n, s
    s c n, s
    sw rd, sw
    sw br 13 28, sw
    s h, x
    w c e, w
    w c e, w
    w c e, w
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    s h, x
    w c e, w
    w c e, w
    w c e, w
    x, x
    x, x
    x, x
    x, x
    x, x
    x, x
    s h, x
    """,
)

register(
    KnownMap.CHEMISTRY_CLASS,
    Opening(
        core_spawns=[(-1, -1), (1, -1), (-1, 1)],
        builder_scripts=[_B1, _B2, _B3],
    ),
)
