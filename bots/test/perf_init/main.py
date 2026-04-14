import time

from cambc import Controller, Direction, EntityType


class Player:
    def __init__(self) -> None:
        self.done = False

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                if not self.done:
                    pos = ct.get_position()
                    target = pos.add(Direction.SOUTH)
                    if ct.can_spawn(target):
                        ct.spawn_builder(target)
                        self.done = True
            case EntityType.BUILDER_BOT:
                from builder import Builder

                t0 = time.perf_counter_ns()
                b = Builder(ct)
                t1 = time.perf_counter_ns()
                ct.resign(f"Builder.__init__={t1 - t0}ns ({(t1 - t0) // 1000}us)")
