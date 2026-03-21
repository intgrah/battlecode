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
        if ti >= cost * 3 and ct.get_current_round() >= self.spawned * 50:
            pos = ct.get_position()
            for d in DIRECTIONS:
                sp = pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return
