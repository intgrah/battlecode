from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    2,
    0,
    """
    e rd, e
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se rd, se
    se h, x
    s rd, s
    se sn s, x
    ne ba, x
    """,
)

register(
    KnownMap.DEFAULT_SMALL1,
    Opening(
        core_spawns=[(1, -1)],
        builder_scripts=[_B1],
    ),
)
