from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2
    ECON_1 = 3
    """Blueprint + econ. Permanent."""
    ECON_2 = 4
    """Blueprint + econ. Non-permanent; transitions into ECON/DEFENSE/OFFENSE."""
    DEFENSE_1 = 5
    """Blueprint + defense. Permanent."""

    def __str__(self) -> str:
        return self.name.lower()
