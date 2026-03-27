from cambc import Controller, Direction, EntityType, Position
from unit import Unit

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.spawned = 0
        self.core_pos: Position = ct.get_position()
        self.nearest_bridge_id: int | None = None
        self.last_resource_turn: int = 0

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        pos = self.core_pos
        my_team = ct.get_team()
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()

        best_bridge = None
        best_bridge_dist = 999999
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
            for d in DIRECTIONS:
                sp = pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    self.last_resource_turn = rnd
                    return

        if (self.spawned < 2 or ct.get_hp() < ct.get_max_hp()) and ti >= cost:
            for d in DIRECTIONS:
                sp = pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return

        if ti > cost + 300 and self.spawned < 2 + rnd // 100:
            for d in DIRECTIONS:
                sp = pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return
