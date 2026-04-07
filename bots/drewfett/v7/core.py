"""Core spawning logic. Ported from v2."""

from cambc import Controller, Direction, Environment, Position
from unit import Unit

_DIRECTIONS = tuple(d for d in Direction if d != Direction.CENTRE)
_BUILDER_CAP = 49

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

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        ti, _ = ct.get_global_resources()
        builder_cost, _ = ct.get_builder_bot_cost()
        alive = ct.get_unit_count() - 1

        if alive >= _BUILDER_CAP:
            return

        my_team = ct.get_team()
        if ct.get_hp() < ct.get_max_hp():
            if ti >= builder_cost:
                self._spawn(ct)
            return

        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                if ti >= builder_cost:
                    self._spawn(ct)
                return

        reserve = 0 if alive < 4 else builder_cost * 6
        if ti < builder_cost + reserve:
            return
        self._spawn(ct)

    def _spawn(self, ct: Controller) -> None:
        sp = _best_spawn_pos(ct, self.core_pos, self.spawned)
        if sp is None:
            return
        ct.spawn_builder(sp)
        self.spawned += 1


def _best_spawn_pos(ct: Controller, pos: Position, spawned: int) -> Position | None:
    n = len(_DIRECTIONS)
    for i in range(n):
        d = _DIRECTIONS[(spawned + i) % n]
        sp = pos.add(d)
        if not ct.can_spawn(sp):
            continue
        w, h = ct.get_map_width(), ct.get_map_height()
        walls = 0
        for d2 in _DIRECTIONS:
            adj = sp.add(d2)
            if not (0 <= adj.x < w and 0 <= adj.y < h):
                walls += 1
                continue
            if not ct.is_in_vision(adj):
                continue
            if ct.get_tile_env(adj) == Environment.WALL:
                walls += 1
        if walls < 6:
            return sp

    for d in _DIRECTIONS:
        sp = pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None
