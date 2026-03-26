from cambc import Direction, EntityType

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

DELTA_TO_DIR = {
    (0, -1): Direction.NORTH,
    (0, 1): Direction.SOUTH,
    (1, 0): Direction.EAST,
    (-1, 0): Direction.WEST,
}

WALKABLE_BUILDINGS = frozenset(
    (
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
    ),
)

DIRECTED_BUILDINGS = frozenset(
    (
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
    ),
)

TRANSPORT = frozenset(
    (
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    ),
)

TURRETS = frozenset(
    (
        EntityType.GUNNER,
        EntityType.SENTINEL,
        EntityType.BREACH,
        EntityType.LAUNCHER,
    ),
)


def tiles_3x3(cx: int, cy: int, w: int, h: int) -> set[int]:
    return {
        (cy + dy) * w + (cx + dx)
        for dx in range(-1, 2)
        for dy in range(-1, 2)
        if 0 <= cx + dx < w and 0 <= cy + dy < h
    }
