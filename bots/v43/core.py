from cambc import Controller, Direction
from entity import Entity

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Core(Entity):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if self.spawned >= 49:
            return
        # Phase 1 (first 6): spawn aggressively for fast harvester placement.
        # Phase 2 (7-20): moderate reserve to sustain building.
        # Phase 3 (21+): only spawn with substantial surplus.
        if self.spawned < 6:
            reserve = cost + 80
        elif self.spawned < 20:
            reserve = cost * 2
        else:
            reserve = cost * 3
        if ti >= reserve:
            pos = ct.get_position()
            for d in DIRECTIONS:
                sp = pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return
