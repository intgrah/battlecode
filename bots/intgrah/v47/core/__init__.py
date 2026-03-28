from cambc import Controller, Direction, Position
from unit import Unit

_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
_INITIAL_BUILDERS = 6
_SPAWN_COOLDOWN = 40
_TI_BUFFER = 400


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.last_spawn_turn: int = 0

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()
        builder_cost, _ = ct.get_builder_bot_cost()
        harvester_cost, _ = ct.get_harvester_cost()

        should_spawn = False

        if rnd < _INITIAL_BUILDERS:
            should_spawn = ti >= builder_cost
        elif rnd - self.last_spawn_turn >= _SPAWN_COOLDOWN:
            should_spawn = ti >= builder_cost + harvester_cost + _TI_BUFFER

        if should_spawn:
            sp = _best_spawn_pos(ct, self.core_pos)
            if sp is not None and ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.last_spawn_turn = rnd


def _best_spawn_pos(ct: Controller, pos: Position) -> Position | None:
    for d in _DIRECTIONS:
        sp = pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None
