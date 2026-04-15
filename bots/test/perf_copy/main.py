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
                k = 1_000_000

                a = [0]
                b = [1]

                t0 = time.perf_counter_ns()
                for _ in range(k):
                    x = a[0]
                t1 = time.perf_counter_ns()
                for _ in range(k):
                    a[0] = b[0]
                t2 = time.perf_counter_ns()
                for _ in range(k):
                    a[:] = b
                t3 = time.perf_counter_ns()
                for _ in range(k):
                    a = b
                t4 = time.perf_counter_ns()

                x = 0
                t5 = time.perf_counter_ns()
                for _ in range(k):
                    y = x
                t6 = time.perf_counter_ns()
                for _ in range(k):
                    x = 1
                t7 = time.perf_counter_ns()

                read_list = (t1 - t0) * 1000 // k
                copy_elem = (t2 - t1) * 1000 // k
                slice_copy = (t3 - t2) * 1000 // k
                rebind = (t4 - t3) * 1000 // k
                read_int = (t6 - t5) * 1000 // k
                write_int = (t7 - t6) * 1000 // k
                ct.resign(
                    f"a[0]_read={read_list}ps "
                    f"a[0]=b[0]={copy_elem}ps "
                    f"a[:]=b={slice_copy}ps "
                    f"a=b={rebind}ps "
                    f"x_read={read_int}ps "
                    f"x=1={write_int}ps"
                )
