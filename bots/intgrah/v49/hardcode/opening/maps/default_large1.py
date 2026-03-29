from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    12,
    24,
    """
    ne rd, ne; ne rd, ne; ne rd, ne; ne rd, ne
    ne rd, ne; ne rd, ne; ne rd, ne; ne rd, ne
    ne rd, ne; ne rd, ne; ne rd, ne; ne rd, ne
    ne rd, ne; ne rd, ne; ne rd, ne; ne rd, ne
    se h, x
    s sn s, x
    e ba, x
    """,
)

register(
    KnownMap.DEFAULT_LARGE1,
    Opening(
        core_spawns=[(1, -1)],
        builder_scripts=[_B1],
    ),
)
