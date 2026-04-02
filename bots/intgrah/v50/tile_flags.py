from typing import Final

from constants import COST_EMPTY, COST_IMPASSABLE, COST_ROAD, COST_UNSEEN

# Top 2 bits: tile category
B_IMPASSABLE_TERRAIN: Final[int] = 0b01_000000
B_PASSABLE: Final[int] = 0b10_000000

# Bit 5: enemy flag (only meaningful when passable + has building)
B_ENEMY: Final[int] = 0b00_1_00000

# Bits 4-0: building type (0 = no building)
B_TYPE_MASK: Final[int] = 0b00_0_11111

# Env-only tiles (no building possible)
UNSEEN: Final[int] = 0b00_000000
WALL: Final[int] = 0b01_000000
ORE_TI: Final[int] = 0b01_000001
ORE_AX: Final[int] = 0b01_000010

# Passable tile, no building
EMPTY: Final[int] = 0b10_000000

# Building types (bits 4-0, 1-based, 0 = no building)
#
# Walkable group: type & 0b11000 == 0, type >= 1
B_ROAD: Final[int] = 0b00001  # 1
B_CONVEYOR: Final[int] = 0b00010  # 2
B_ARMOURED_CONVEYOR: Final[int] = 0b00011  # 3
B_SPLITTER: Final[int] = 0b00100  # 4
B_BRIDGE: Final[int] = 0b00101  # 5
B_CORE: Final[int] = 0b00110  # 6
B_MARKER: Final[int] = 0b00111  # 7
#
# Blocking group: type & 0b11000 == 0b01000
B_BARRIER: Final[int] = 0b01000  # 8
B_HARVESTER_TI: Final[int] = 0b01001  # 9
B_HARVESTER_AX: Final[int] = 0b01010  # 10
B_FOUNDRY: Final[int] = 0b01011  # 11
#
# Turret group: type & 0b11000 == 0b10000
B_GUNNER: Final[int] = 0b10000  # 16
B_SENTINEL: Final[int] = 0b10001  # 17
B_BREACH: Final[int] = 0b10010  # 18
B_LAUNCHER: Final[int] = 0b10011  # 19


def make_building(building_type: int, *, enemy: bool = False) -> int:
    f = B_PASSABLE | building_type
    if enemy:
        f |= B_ENEMY
    return f


# --- Single-operation queries ---


def is_unseen(f: int) -> bool:
    return f == 0


def is_wall_or_ore(f: int) -> bool:
    return (f & B_IMPASSABLE_TERRAIN) == B_IMPASSABLE_TERRAIN


def is_passable(f: int) -> bool:
    return (f & B_PASSABLE) != 0


def has_building(f: int) -> bool:
    return (f & B_PASSABLE) != 0 and (f & B_TYPE_MASK) != 0


def is_enemy(f: int) -> bool:
    return (f & B_ENEMY) != 0


def is_friendly(f: int) -> bool:
    return (f & (B_PASSABLE | B_ENEMY)) == B_PASSABLE and (f & B_TYPE_MASK) != 0


def building_type(f: int) -> int:
    return f & B_TYPE_MASK


# Masks using type group bits (bits 4-3 of type)
def is_transport(f: int) -> bool:
    t = f & B_TYPE_MASK
    return (f & B_PASSABLE) != 0 and B_CONVEYOR <= t <= B_BRIDGE


def is_turret(f: int) -> bool:
    return (f & B_PASSABLE) != 0 and (f & B_TYPE_MASK) & 0b11000 == 0b10000


def is_harvester(f: int) -> bool:
    t = f & B_TYPE_MASK
    return (f & B_PASSABLE) != 0 and (t in (B_HARVESTER_TI, B_HARVESTER_AX))


def is_walkable_building(f: int) -> bool:
    if (f & B_PASSABLE) == 0 or (f & B_ENEMY) != 0:
        return False
    t = f & B_TYPE_MASK
    return B_ROAD <= t <= B_CORE


# --- Walk cost lookup table (one read, no branching) ---

WALK_COST: Final[list[int]] = [0] * 256
for _b in range(256):
    if _b == 0:
        WALK_COST[_b] = COST_UNSEEN
    elif (_b & B_IMPASSABLE_TERRAIN) == B_IMPASSABLE_TERRAIN:
        WALK_COST[_b] = COST_IMPASSABLE
    elif (_b & B_PASSABLE) == 0:
        WALK_COST[_b] = COST_UNSEEN
    else:
        _t = _b & B_TYPE_MASK
        _enemy = (_b & B_ENEMY) != 0
        if _t in (0, B_MARKER):
            WALK_COST[_b] = COST_EMPTY
        elif not _enemy and B_ROAD <= _t <= B_CORE:
            WALK_COST[_b] = COST_ROAD
        else:
            WALK_COST[_b] = COST_IMPASSABLE
