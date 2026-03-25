from cambc import Direction

DIR4 = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
DIR4_DELTA = [c.delta() for c in DIR4]
DIR8 = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
DIR8_DELTA = [c.delta() for c in DIR8]

BRIDGE_DELTAS = [
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 2 < dx * dx + dy * dy <= 9
]
