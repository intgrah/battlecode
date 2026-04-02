from enum import StrEnum


class Task(StrEnum):
    CONNECT_EXCESS_TI = "connect_excess_ti"
    CONNECT_EXCESS_AX = "connect_excess_ax"
    HARVEST_TI = "harvest_ti"
    HARVEST_AX = "harvest_ax"
    EXPLORE = "explore"
    PATROL = "patrol"
    HEAL_CORE = "heal_core"
    PLACE_LAUNCHER = "place_launcher"
    BARRIER_ORE = "barrier_ore"
    FIRE_ENEMY_TRANSPORT = "fire_enemy_transport"
    PLACE_SENTINEL = "place_sentinel"
    HEAL_TURRET = "heal_turret"
