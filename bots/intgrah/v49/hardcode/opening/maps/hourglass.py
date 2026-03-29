from hardcode.known import KnownMap

from hardcode.opening import Opening, register
from .parse import parse_script

_WALK_N = "n rd, n; " * 35

_B1 = parse_script(
    13,
    42,
    _WALK_N + "n h, x; ne ba, x; x, s; n ba, x",
)

_B2 = parse_script(
    12,
    42,
    _WALK_N + "n ba, x; nw rd, nw; ne rd, ne; e sn n, x",
)

register(
    KnownMap.HOURGLASS,
    Opening(
        core_spawns=[(0, -1), (-1, -1)],
        builder_scripts=[_B1, _B2],
    ),
)
