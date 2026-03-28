from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    3,
    3,
    """
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    s rd, s
    w rd, w
    sw rd, sw
    se rd, se
    se rd, se
    e rd, e
    se rd, se
    e rd, e
    ne rd, ne
    e rd, e
    e h, x
    se sn se, x
    """,
)

register(
    KnownMap.SHISH_KEBAB,
    Opening(
        core_spawns=[(1, 1)],
        builder_scripts=[_B1],
    ),
)
