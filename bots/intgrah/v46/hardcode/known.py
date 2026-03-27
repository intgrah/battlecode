from cambc import Position

type MapKey = tuple[int, int, Position]


class KnownMap:
    __slots__ = ()

    ARENA: MapKey = (25, 25, Position(8, 10))
    BATTLEBOT: MapKey = (21, 29, Position(4, 4))
    CHEMISTRY_CLASS: MapKey = (40, 40, Position(14, 23))
    CINNAMON_ROLL: MapKey = (30, 30, Position(2, 27))
    CORRIDORS: MapKey = (31, 31, Position(5, 15))
    DEFAULT_LARGE1: MapKey = (40, 40, Position(11, 25))
    DEFAULT_LARGE2: MapKey = (50, 30, Position(3, 16))
    DEFAULT_MEDIUM1: MapKey = (30, 30, Position(10, 19))
    DEFAULT_MEDIUM2: MapKey = (30, 30, Position(3, 3))
    DEFAULT_SMALL1: MapKey = (20, 20, Position(1, 1))
    DEFAULT_SMALL2: MapKey = (21, 21, Position(10, 1))
    DNA: MapKey = (21, 50, Position(10, 48))
    FACE: MapKey = (20, 20, Position(5, 7))
    GALAXY: MapKey = (40, 40, Position(4, 35))
    HOOKS: MapKey = (31, 31, Position(3, 22))
    HOURGLASS: MapKey = (27, 45, Position(13, 43))
    LANDSCAPE: MapKey = (30, 30, Position(3, 2))
    MINIMAZE: MapKey = (25, 25, Position(1, 23))
    PLS_BUY_CUCATS_MERCH: MapKey = (49, 49, Position(13, 17))
    SHISH_KEBAB: MapKey = (20, 20, Position(2, 2))
    THREAD_OF_CONNECTION: MapKey = (20, 20, Position(3, 16))
    TREE_OF_LIFE: MapKey = (39, 30, Position(4, 22))
    WASTELAND: MapKey = (40, 40, Position(3, 36))
