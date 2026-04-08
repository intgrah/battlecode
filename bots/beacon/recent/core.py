"""Core spawning logic. Ported from v2."""

from cambc import Controller, Direction, Environment, Position
from unit import Unit

_DIRECTIONS = tuple(d for d in Direction if d != Direction.CENTRE)
_BUILDER_CAP = 30

ROLE_ECON = 0
ROLE_ATTACK = 1
ROLE_DEFENSE = 2

# Spawn 0-2: ECON, 3-5: ATTACK, 6: DEFENSE, 7+: ATTACK
_INITIAL_ROLES: tuple[int, ...] = (
    ROLE_ECON,
    ROLE_ECON,
    ROLE_ATTACK,
    ROLE_DEFENSE,
    ROLE_ECON,
    ROLE_DEFENSE,
    ROLE_ATTACK,
)


_LATE_CYCLE: tuple[int, ...] = (ROLE_DEFENSE, ROLE_ATTACK)


def role_for_spawn(index: int) -> int:
    """Return the role for the *index*-th spawned builder (0-based)."""
    if index < len(_INITIAL_ROLES):
        return _INITIAL_ROLES[index]
    return _LATE_CYCLE[(index - len(_INITIAL_ROLES)) % len(_LATE_CYCLE)]


# Direction offset -> spawn index (clockwise from N, matches _DIRECTIONS order)
OFFSET_TO_INDEX: dict[tuple[int, int], int] = {
    d.delta(): i for i, d in enumerate(_DIRECTIONS)
}


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.spawned: int = 0
        self._blocked_turns: int = 0

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        ti, _ = ct.get_global_resources()
        builder_cost, _ = ct.get_builder_bot_cost()
        alive = ct.get_unit_count() - 1

        if alive >= _BUILDER_CAP:
            return

        my_team = ct.get_team()

        # Emergency: core damaged — spawn with small reserve
        if ct.get_hp() < ct.get_max_hp():
            if ti >= builder_cost * 2:
                self._spawn(ct)
            return

        # Normal: maintain reserve before spawning
        reserve = 0 if alive < 4 else builder_cost * 6
        if ti < builder_cost + reserve:
            return
        self._spawn(ct)

    def _spawn(self, ct: Controller) -> None:
        sp = _best_spawn_pos(ct, self.core_pos, self.spawned, self._blocked_turns)
        if sp is None:
            self._blocked_turns += 1
            return
        ct.spawn_builder(sp)
        self.spawned += 1
        self._blocked_turns = 0


# Precompute: for each role, which direction indices produce it
_ROLE_TO_INDICES: dict[int, list[int]] = {}
for _i, _d in enumerate(_DIRECTIONS):
    _r = role_for_spawn(_i)
    _ROLE_TO_INDICES.setdefault(_r, []).append(_i)


def _best_spawn_pos(
    ct: Controller, pos: Position, spawned: int, blocked_turns: int
) -> Position | None:
    """Pick a spawn tile that maps to the desired role."""
    desired_role = role_for_spawn(spawned)

    # Try tiles that produce the desired role first
    for idx in _ROLE_TO_INDICES.get(desired_role, []):
        sp = pos.add(_DIRECTIONS[idx])
        if ct.can_spawn(sp):
            return sp

    # Only fallback to wrong-role tile after 5 blocked turns
    if blocked_turns >= 5:
        for d in _DIRECTIONS:
            sp = pos.add(d)
            if ct.can_spawn(sp):
                return sp
    return None
