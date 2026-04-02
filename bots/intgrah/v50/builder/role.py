from enum import IntEnum


class Role(IntEnum):
    ECON = 0
    DEFENSE = 1
    OFFENSE = 2

    def __str__(self) -> str:
        return self.name.lower()


ROLE_TARGETS: dict[Role, int] = {
    Role.ECON: 5,
    Role.DEFENSE: 3,
    Role.OFFENSE: 2,
}

ROLE_TARGET_TOTAL: int = sum(ROLE_TARGETS.values())


def initial_role(birthday: int) -> Role:
    """Deterministic role from birthday, matching ROLE_TARGETS ratio."""
    bucket = birthday % ROLE_TARGET_TOTAL
    cumulative = 0
    for role, weight in ROLE_TARGETS.items():
        cumulative += weight
        if bucket < cumulative:
            return role
    raise AssertionError
