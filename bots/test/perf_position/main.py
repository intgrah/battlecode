import time

from cambc import Controller, EntityType


class Player:
    def __init__(self) -> None:
        self.done = False
        self.my_pos = None

    def run(self, ct: Controller) -> None:
        if self.done:
            return

        match ct.get_entity_type():
            case EntityType.CORE:
                pos = ct.get_position()
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
            case EntityType.BUILDER_BOT:
                self.done = True
                self.my_pos = ct.get_position()
                n = 100_000

                t0 = time.perf_counter_ns()
                for _ in range(n):
                    ct.get_position()
                t1 = time.perf_counter_ns()
                for _ in range(n):
                    _ = self.my_pos
                t2 = time.perf_counter_ns()

                ct_ns = t1 - t0
                self_ns = t2 - t1
                ct.resign(
                    f"ct.get_position={ct_ns // n}ns/call"
                    f" self.my_pos={self_ns // n}ns/call"
                    f" n={n}"
                )
