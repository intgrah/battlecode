from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

_B1 = parse_script(
    4,
    15,
    """
    ne rd, ne; ne rd, ne; ne rd, ne; n rd, n
    nw rd, nw; nw rd, nw; n rd, n; nw rd, nw
    nw rd, nw; ne rd, ne; e rd, e; se rd, se
    se rd, se; se rd, se; se rd, se; se rd, se
    se rd, se; se rd, se; se rd, se; se rd, se
    e rd, e; ne rd, ne; ne rd, ne; ne rd, ne
    n rd, n; nw rd, nw; nw rd, nw; nw rd, nw
    nw rd, nw; nw rd, nw
    ne rd, ne; nw ba, sw; n h, x; nw ba, x
    e rd, e; n sn e, x; w ba, x
    """,
)

register(
    KnownMap.THREAD_OF_CONNECTION,
    Opening(
        core_spawns=[(1, -1)],
        builder_scripts=[_B1],
    ),
)
