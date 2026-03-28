from cambc import Controller, Position
from entity import Entity


class Core(Entity):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.spawned = False

    def run(self, ct: Controller) -> None:
        if self.spawned:
            return
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if ti >= cost:
            pos = ct.get_position()
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    sp = Position(pos.x + dx, pos.y + dy)
                    if ct.can_spawn(sp):
                        ct.spawn_builder(sp)
                        self.spawned = True
                        return
