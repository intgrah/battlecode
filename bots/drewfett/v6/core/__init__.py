from cambc import Controller, Direction, EntityType, Position
from unit import Unit

_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        self._run_default(ct, ct.get_current_round())

    def _run_default(self, ct: Controller, rnd: int) -> None:
        if ct.get_action_cooldown() != 0:
            return

        ti, _ = ct.get_global_resources()
        builder_cost, _ = ct.get_builder_bot_cost()
        alive = ct.get_unit_count() - 1  # exclude core

        if alive >= 6:
            return

        # Emergency: enemy bots near core → spawn immediately
        my_team = ct.get_team()
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                if ti >= builder_cost:
                    sp = _best_spawn_pos(ct, self.core_pos)
                    if sp is not None:
                        ct.spawn_builder(sp)
                        self.spawned += 1
                return

        # Aggressive: first 3 with zero reserve, rest with small reserve
        h_cost, _ = ct.get_harvester_cost()
        c_cost, _ = ct.get_conveyor_cost()
        reserve = 0 if alive < 3 else h_cost + c_cost * 3

        if ti < builder_cost + reserve:
            return

        sp = _best_spawn_pos(ct, self.core_pos)
        if sp is not None:
            ct.spawn_builder(sp)
            self.spawned += 1


def _best_spawn_pos(ct: Controller, pos: Position) -> Position | None:
    for d in _DIRECTIONS:
        sp = pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None
