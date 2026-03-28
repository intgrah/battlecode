from cambc import Controller, Direction, EntityType, Position, Team
from hardcode.known import KnownMap
from hardcode.map import SYMMETRY
from opening import Opening, get_opening
from opening.identify import identify_map
from opening.mirror import mirror_opening
from unit import Unit
from util import INF

_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
_MARKER_OFFSETS = ((-2, -2), (2, 2), (-2, 2), (2, -2))


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
                w = ct.get_map_width()
                h = ct.get_map_height()
                opening = mirror_opening(opening, w, h, SYMMETRY[km])
            self.opening = opening

            marker_val = list(KnownMap).index(km)
            for odx, ody in _MARKER_OFFSETS:
                mp = Position(self.core_pos.x + odx, self.core_pos.y + ody)
                if ct.can_place_marker(mp):
                    ct.place_marker(mp, marker_val)
                    break

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()

        if self.opening is not None and rnd < len(self.opening.core_spawns):
            self._run_opening(ct, rnd)
            return

        if self.opening is not None:
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
            self.core_pos.x + spawn_offset[0], self.core_pos.y + spawn_offset[1]
        )
        if ct.can_spawn(sp):
            ct.spawn_builder(sp)
            self.spawned += 1

    def _run_default(self, ct: Controller, rnd: int) -> None:
        pos = self.core_pos
        my_team = ct.get_team()
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()

        best_bridge = None
        best_bridge_dist = INF
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) != EntityType.BRIDGE
                or ct.get_team(bid) != my_team
            ):
                continue
            bp = ct.get_position(bid)
            d = max(abs(bp.x - pos.x), abs(bp.y - pos.y))
            if d < best_bridge_dist:
                best_bridge_dist = d
                best_bridge = bid

        if best_bridge is not None:
            self.nearest_bridge_id = best_bridge
            if ct.get_stored_resource(best_bridge) is not None:
                self.last_resource_turn = rnd

        bridge_destroyed = self.nearest_bridge_id is not None and best_bridge is None
        bridge_starved = (
            self.nearest_bridge_id is not None and rnd - self.last_resource_turn >= 5
        )

        if (bridge_starved or bridge_destroyed) and ti >= cost:
            sp = _best_spawn_pos(ct, pos)
            if sp is not None:
                ct.spawn_builder(sp)
                self.spawned += 1
                self.last_resource_turn = rnd
                return

        if (self.spawned < 2 or ct.get_hp() < ct.get_max_hp()) and ti >= cost:
            sp = _best_spawn_pos(ct, pos)
            if sp is not None:
                ct.spawn_builder(sp)
                self.spawned += 1
                return

        if ti > cost + 300 and self.spawned < 2 + rnd // 100:
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
