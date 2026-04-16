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
                pos = ct.get_position()
                k = 100_000
                nbs = [pos.add(d) for d in Direction if d != Direction.CENTRE]
                t = tuple(nbs)
                l = list(nbs)
                fs = frozenset(nbs)
                target = nbs[0]

                t0 = time.perf_counter_ns()
                for _ in range(k):
                    target in t
                t1 = time.perf_counter_ns()
                for _ in range(k):
                    target in l
                t2 = time.perf_counter_ns()
                for _ in range(k):
                    target in fs
                t3 = time.perf_counter_ns()
                for _ in range(k):
                    for _ in t:
                        pass
                t4 = time.perf_counter_ns()
                for _ in range(k):
                    for _ in l:
                        pass
                t5 = time.perf_counter_ns()
                for _ in range(k):
                    for _ in fs:
                        pass
                t6 = time.perf_counter_ns()

                ct.resign(
                    f"IN t={((t1 - t0) * 10) // k} l={((t2 - t1) * 10) // k} f={((t3 - t2) * 10) // k} "
                    f"IT t={((t4 - t3) * 10) // k} l={((t5 - t4) * 10) // k} f={((t6 - t5) * 10) // k}"
                )
