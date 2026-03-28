from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    4,
    4,
    """
    se rd, se
    se rd, se
    se h, x
    s c w, s
    w br 4 5, x
    """,
)

_B2 = parse_script(
    3,
    4,
    """
    x, e
    s c n, x
    """,
)

register(
    KnownMap.DEFAULT_MEDIUM2,
    Opening(
        core_spawns=[(1, 1), (0, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
