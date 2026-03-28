from hardcode.known import KnownMap

from . import Opening, register
from .parse import parse_script

# battlebot: 21x29, core A at (4,4), core E at (16,4)
# Centre Ti ores: (10,4), (10,6), (10,8)
#
# Bot 1 (spawn 5,4): rush east, harvester (10,4), sentinel (10,3) E, barrier (10,5)
# Bot 2 (spawn 5,5): go east on own road row 5, then barrier ores (10,6) and (10,8)

_B1 = parse_script(
    5,
    4,
    """
    e rd, e
    e rd, e
    e rd, e
    e rd, e
    e h, x
    ne sn e, x
    se ba, x
    """,
)

_B2 = parse_script(
    5,
    5,
    """
    e rd, e
    e rd, e
    e rd, e
    e rd, e
    se ba, x
    s rd, s
    s rd, s
    se ba, x
    """,
)
# T2: road(6,5) E to (6,5)
# T3: road(7,5) E to (7,5)
# T4: road(8,5) E to (8,5)
# T5: road(9,5) E to (9,5)
# T6: barrier(10,6) ON ore, S to (9,6)
# T7: road(9,7) S to (9,7)
# T8: barrier(10,8) ON ore, S to (9,8)... wait, (10,8) is SE from (9,7), not SE from (9,7)
# From (9,7): SE = (10,8). Yes! barrier on ore. Move S to (9,8).
# T9: road(9,9)? No, (10,8) is already done.
# Actually: T6 barrier (10,6), move S to (9,6). T7 road(9,7), move S to (9,7). T8 barrier (10,8), move S.
# But from (9,7): se ba = (10,8) barrier.

register(
    KnownMap.BATTLEBOT,
    Opening(
        core_spawns=[(1, 0), (1, 1)],
        builder_scripts=[_B1, _B2],
    ),
)
