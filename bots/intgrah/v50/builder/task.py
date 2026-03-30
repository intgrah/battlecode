from enum import IntEnum, auto


class Task(IntEnum):
    CONNECT_EXCESS_TI = auto()
    CONNECT_EXCESS_TI_BRIDGE = auto()
    CONNECT_EXCESS_AX = auto()
    HARVEST_TI = auto()
    HARVEST_AX = auto()
    SELF_DESTRUCT = auto()
    EXPLORE = auto()
    PATROL = auto()
    NAV_ENEMY_CORE = auto()
    PLACE_FOUNDRY_TI_CONV = auto()
    PLACE_FOUNDRY_MIXED_CONV = auto()
    PLACE_SPLITTER_FOUNDRY = auto()
    HEAL_CORE = auto()
    SECURE_ORE = auto()
    PLACE_LAUNCHER = auto()
    DENY_ENEMY_HARVESTER = auto()
    BARRIER_ORE = auto()
    FIRE_ENEMY_TRANSPORT = auto()
    PLACE_SENTINEL = auto()
    HEAL_TURRET = auto()
