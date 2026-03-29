from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_B1 = parse_script(
    9,
    0,
    """
    w rd, w; w rd, w; sw rd, sw; sw rd, sw; sw rd, sw; sw rd, sw; sw rd, sw
    sw rd, sw; sw rd, sw; s rd, s; s rd, s; s rd, s; s rd, s; s rd, s; s rd, s
    se rd, se; se rd, se; se rd, se; se rd, se; se rd, se
    ne rd, ne; ne rd, ne; ne rd, ne; e rd, e
    sw rd, x; e ba, sw; se rd, se
    n ba, x; ne h, x; e sn s, x
    """,
)

_B2 = parse_script(
    11,
    0,
    """
    e rd, e; e rd, e; se rd, se; se rd, se; se rd, se; s rd, s
    sw rd, sw; sw rd, sw; sw rd, sw; sw rd, sw; sw rd, sw; sw rd, sw
    se rd, se; se rd, se; se rd, se; se rd, se; se rd, se; se rd, se
    s rd, s; sw rd, sw; nw rd, nw; nw rd, nw; w rd, w; sw rd, sw
    n ba, x
    """,
)

register(
    KnownMap.DEFAULT_SMALL2,
    Opening(
        core_spawns=[(-1, -1), (1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
