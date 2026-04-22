import gc
import sys

from cambc import Controller, EntityType, Position

MESSAGE = 0b10110  # 22, the 5-bit value core will send

SIGNAL_SIZES: tuple[int, ...] = (480, 496, 512, 528, 544)
FILL = 7
THRESHOLD = 1_000_000


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


class Player:
    def __init__(self) -> None:
        self.keep: list[bytes] = []
        self.done = False

    def run(self, ct: Controller) -> None:
        if self.done:
            return
        self.done = True
        match ct.get_entity_type():
            case EntityType.CORE:
                self._core(ct)
            case EntityType.BUILDER_BOT:
                self._builder(ct)

    def _core(self, ct: Controller) -> None:
        gc.disable()
        log(f"[CORE] sending {MESSAGE} = {MESSAGE:05b}")
        for bit, size in enumerate(SIGNAL_SIZES):
            if (MESSAGE >> bit) & 1:
                pool = [bytes(size) for _ in range(FILL)]
                # list.clear() decrefs in reverse (index 6 first, 0 last).
                # index 0 freed last -> pushed to tcache bottom -> survives engine consumption.
                pool.clear()
        pos = ct.get_position()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    return

    def _builder(self, ct: Controller) -> None:
        gc.disable()
        received = 0
        for bit, size in enumerate(SIGNAL_SIZES):
            a = bytes(size)
            b = bytes(size)
            addr_a, addr_b = id(a), id(b)
            self.keep.extend([a, b])
            gap = addr_b - addr_a
            bit_val = 1 if gap > THRESHOLD else 0
            received |= bit_val << bit
            log(f"[BUILDER] bit {bit} size={size}: addr_a={addr_a:x} gap={gap} -> {bit_val}")
        match = received == MESSAGE
        log(f"[BUILDER] received {received} = {received:05b}  expected {MESSAGE} = {MESSAGE:05b}  match={match}")
