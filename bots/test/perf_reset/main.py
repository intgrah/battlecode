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
                    if ct.can_spawn(pos.add(Direction.SOUTH)):
                        ct.spawn_builder(pos.add(Direction.SOUTH))
                        self.done = True
            case EntityType.BUILDER_BOT:
                INF = 1_000_000
                n = 2500
                dist = [INF] * n
                reset_list = [INF] * n
                reset_tuple = (INF,) * n

                k = 10000
                t0 = time.perf_counter_ns()
                for _ in range(k):
                    dist[:] = reset_list
                t1 = time.perf_counter_ns()
                for _ in range(k):
                    dist[:] = reset_tuple
                t2 = time.perf_counter_ns()

                list_ns = (t1 - t0) // k
                tuple_ns = (t2 - t1) // k
                ct.resign(f"n={n} list={list_ns}ns tuple={tuple_ns}ns")
