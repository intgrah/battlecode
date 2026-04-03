from cambc import Controller, Direction, Position, Team
from config import OPENING, OpeningMode
from hardcode.map import SYMMETRY
from hardcode.opening import Opening, get_opening
from hardcode.opening.identify import identify_map
from hardcode.opening.mirror import mirror_opening
from unit import Unit

_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.spawned = 0
        self.nearest_bridge_id: int | None = None
        self.last_resource_turn: int = 0

        km = identify_map(ct, self.core_pos)
        self.opening: Opening | None = None

        if km is not None:
            opening = get_opening(km)
            if opening is not None and ct.get_team() == Team.B:
                opening = mirror_opening(opening, SYMMETRY[km])
            self.opening = opening

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()

        if (
            OPENING != OpeningMode.OFF
            and self.opening is not None
            and rnd < len(self.opening.core_spawns)
        ):
            self._run_opening(ct, rnd)
            return

        self._run_default(ct, rnd)

    def _run_opening(self, ct: Controller, rnd: int) -> None:
        assert self.opening is not None
        spawn_offset = self.opening.core_spawns[rnd]
        if spawn_offset is None:
            return
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if ti < cost:
            return
        sp = Position(
            self.core_pos.x + spawn_offset[0],
            self.core_pos.y + spawn_offset[1],
        )
        if ct.can_spawn(sp):
            ct.spawn_builder(sp)
            self.spawned += 1

    def _run_default(self, ct: Controller, _rnd: int) -> None:
        if self.spawned >= 20:
            return
        pos = self.core_pos
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        reserve = 0 if self.spawned < 3 else cost * 3
        if ti >= cost + reserve:
            sp = _best_spawn_pos(ct, pos)
            if sp is not None:
                ct.spawn_builder(sp)
                self.spawned += 1


def _best_spawn_pos(ct: Controller, pos: Position) -> Position | None:
    for d in _DIRECTIONS:
        sp = pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None
