from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    4,
    21,
    """
    ne rd, ne; ne rd, ne; e rd, e; e rd, e
    se rd, se; se rd, se; se rd, se; se rd, se
    e rd, e; e rd, e; ne rd, ne; n rd, n
    n rd, n; n rd, n; ne rd, ne; ne rd, ne
    e rd, e; e rd, e; e rd, e; e rd, e
    e rd, e; ne rd, ne; ne rd, ne
    se h, x; s ba, x; e c n, e; se ba, x; n sn n, x
    """,
)

register(
    KnownMap.HOOKS,
    Opening(
        core_spawns=[(1, -1)],
        builder_scripts=[_B1],
    ),
)
