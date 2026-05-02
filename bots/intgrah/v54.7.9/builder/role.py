from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    PUSH = 2
    PERM_ECON = 3
    PERM_DEFENSE = 4
    PARASITIC = 5
    ECON_REACTIVE = 6
    """ECON that auto-flips to DEFENSE at round > 25. Used for the
    third opening builder so it gathers map intel as ECON early, then
    pivots to DEFENSE with a real picture of the economic terrain."""

    def __str__(self) -> str:
        return self.name.lower()

    def is_offensive(self) -> bool:
        return self in (Role.PUSH, Role.PARASITIC)
