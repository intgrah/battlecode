from enum import IntEnum, auto


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2


# Target ratio for role distribution (role, weight).
ROLE_TARGETS: tuple[tuple[Role, int], ...] = (
    (Role.ECON, 5),
    (Role.DEFENSE, 3),
    (Role.OFFENSE, 2),
)

_TARGET_TOTAL: int = sum(t for _, t in ROLE_TARGETS)


def initial_role(birthday: int) -> Role:
    """Deterministic role from birthday, matching ROLE_TARGETS ratio."""
    bucket = birthday % _TARGET_TOTAL
    cumulative = 0
    for role, weight in ROLE_TARGETS:
        cumulative += weight
        if bucket < cumulative:
            return role
    return ROLE_TARGETS[-1][0]


class Task(IntEnum):
    CONNECT_EXCESS_TI = auto()
    CONNECT_EXCESS_AX = auto()
    HARVEST_TI = auto()
    HARVEST_AX = auto()
    EXPLORE = auto()
    PATROL = auto()
    HEAL_CORE = auto()
    PLACE_LAUNCHER = auto()
    BARRIER_ORE = auto()
    FIRE_ENEMY_TRANSPORT = auto()
    PLACE_SENTINEL = auto()
    HEAL_TURRET = auto()
