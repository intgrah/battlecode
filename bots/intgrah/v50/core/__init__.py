from cambc import Controller, Direction, EntityType, Position, Team
from config import OPENING, OpeningMode
from hardcode.known import KnownMap
from hardcode.map import SYMMETRY
from hardcode.opening import Opening, get_opening
from hardcode.opening.identify import identify_map
from hardcode.opening.mirror import mirror_opening
from marker import MarkerOpeningBook
from unit import Unit

_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
_MARKER_OFFSETS = ((2, 2), (-2, -2), (2, -2), (-2, 2), (0, 2), (0, -2), (2, 0), (-2, 0))


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.spawned = 0
        self.nearest_bridge_id: int | None = None
        self.last_resource_turn: int = 0

        km = identify_map(ct, self.core_pos)
        self.opening: Opening | None = None
        self._marker_val: int | None = None

        if km is not None:
            opening = get_opening(km)
            if opening is not None and ct.get_team() == Team.B:
                opening = mirror_opening(opening, SYMMETRY[km])
            self.opening = opening
            self._marker_val = MarkerOpeningBook(list(KnownMap).index(km)).encode()
            self._place_marker(ct)

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()

        if OPENING != OpeningMode.OFF and self.opening is not None:
            if rnd < len(self.opening.core_spawns):
                self._run_opening(ct, rnd)
                return
            if rnd <= len(self.opening.core_spawns) + 1:
                self._place_marker(ct)
                return

        self._run_default(ct, rnd)

    def _place_marker(self, ct: Controller) -> None:
        if self._marker_val is None:
            return
        for odx, ody in _MARKER_OFFSETS:
            mp = Position(self.core_pos.x + odx, self.core_pos.y + ody)
            w, h = ct.get_map_width(), ct.get_map_height()
            if not (0 <= mp.x < w and 0 <= mp.y < h):
                continue
            bid = ct.get_tile_building_id(mp)
            if bid is not None:
                if (
                    ct.get_entity_type(bid) == EntityType.MARKER
                    and ct.get_team(bid) == ct.get_team()
                ):
                    return
                continue
            if ct.can_place_marker(mp):
                ct.place_marker(mp, self._marker_val)
                return

    def _run_opening(self, ct: Controller, rnd: int) -> None:
        assert self.opening is not None
        self._place_marker(ct)
        spawn_offset = self.opening.core_spawns[rnd]
        if spawn_offset is None:
            return
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if ti < cost:
            return
        sp = Position(
            self.core_pos.x + spawn_offset[0], self.core_pos.y + spawn_offset[1]
        )
        if ct.can_spawn(sp):
            ct.spawn_builder(sp)
            self.spawned += 1

    def _run_default(self, ct: Controller, _rnd: int) -> None:
        if self.spawned >= 3:
            return
        pos = self.core_pos
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if ti >= cost:
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
