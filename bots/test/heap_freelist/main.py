import gc
import sys

from cambc import Controller, EntityType, Position

SIZE = 480  # getsizeof=513 -> glibc chunk 528
CHUNK = 528
POOL = 7  # tcache max; filler trick sets k=5, so pool[3] always survives engine
DRAIN = 3000  # exhaust any lingering 528-byte chunks from Python init
PREDRAIN = 7  # empty tcache[528] after DRAIN's list-resize side effects
NUM_BITS = 4
NUM_POOLS = 5  # pool_2 is decoy: engine wild-frees it in round 3; pool_4 absorbs any tail disturbances
MESSAGE = 10  # 0b1010
STRIDE = (POOL + 1) * CHUNK  # 8 * 528 = 4224; pool_i[3] = pool_0[3] + i * STRIDE


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


class Player:
    def __init__(self) -> None:
        self._pools: list[list[bytes | None]] = []
        self._pool_addrs: list[list[int]] = []
        self._guards: list[bytes] = []
        self.keep: list[bytes] = []
        self.round = 0
        self.spawned = False
        self._base_target: int = 0
        self._bits: list[int] = []

    def run(self, ct: Controller) -> None:
        self.round += 1
        match ct.get_entity_type():
            case EntityType.CORE:
                self._core(ct)
            case EntityType.BUILDER_BOT:
                self._builder(ct)

    def _core(self, ct: Controller) -> None:
        gc.disable()
        if self.round == 1:
            self._setup(ct)
        elif 2 <= self.round <= NUM_BITS + 1:
            self._send_bit(self.round - 2)

    def _setup(self, ct: Controller) -> None:
        # exhaust smallbins/unsorted bin in 528-byte class from Python init
        drain: list[bytes] = [bytes(SIZE) for _ in range(DRAIN)]
        self.keep.extend(drain)
        # empty tcache[528] (large drain's list-resize side effects put ~1 entry there)
        predrain: list[bytes] = [bytes(SIZE) for _ in range(PREDRAIN)]
        self.keep.extend(predrain)

        # allocate 5 pools + guards sequentially from OS (tcache is now empty)
        for i in range(NUM_POOLS):
            pool: list[bytes | None] = [bytes(SIZE) for _ in range(POOL)]
            addrs = [id(b) for b in pool]
            strides = [addrs[j] - addrs[j - 1] for j in range(1, POOL)]
            if not all(s == CHUNK for s in strides):
                log(f"[CORE r1] ERROR pool_{i} not sequential: {set(strides)}")
            self._pools.append(pool)
            self._pool_addrs.append(addrs)
            if i < NUM_POOLS - 1:
                guard = bytes(SIZE)
                self._guards.append(guard)
                self.keep.append(guard)

        for _ in range(POOL + 1):
            self.keep.append(bytes(SIZE))

        self._base_target = self._pool_addrs[0][3]
        log(f"[CORE r1] pool_0[3]={self._base_target:x} stride={STRIDE}")
        for i in range(NUM_POOLS):
            t = self._base_target + i * STRIDE
            log(
                f"[CORE r1] target_{i}={t:x} pool_{i}[3]={self._pool_addrs[i][3]:x} match={t == self._pool_addrs[i][3]}"
            )

        pos = ct.get_position()
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if dx * dx + dy * dy > 8:
                    continue
                if abs(dx) <= 1 and abs(dy) <= 1:
                    continue
                tile = Position(pos.x + dx, pos.y + dy)
                if ct.can_place_marker(tile):
                    ct.place_marker(tile, self._base_target & 0xFFFFFFFF)
                    log(
                        f"[CORE r1] marker at ({tile.x},{tile.y}) val={self._base_target & 0xFFFFFFFF:x}"
                    )
                    break

        if not self.spawned:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    p = Position(pos.x + dx, pos.y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        self.spawned = True
                        break
                if self.spawned:
                    break

    def _send_bit(self, bit_index: int) -> None:
        # pool_2 is wild-freed by engine in round 3; skip it for data bits
        pi = bit_index if bit_index <= 1 else bit_index + 1
        pool_i = self._pools[pi]
        addrs_i = self._pool_addrs[pi]
        bit = (MESSAGE >> (NUM_BITS - 1 - bit_index)) & 1
        log(f"[CORE r{self.round}] bit[{bit_index}]={bit} target={addrs_i[3]:x}")
        if bit == 1:
            temp: list[bytes] = [bytes(SIZE) for _ in range(POOL)]
            self.keep.extend(temp)
            filler = [bytes(SIZE) for _ in range(5)]
            filler.clear()
            for j in range(POOL):
                obj = pool_i[j]
                pool_i[j] = None
                del obj

    def _builder(self, ct: Controller) -> None:
        gc.disable()
        r = ct.get_current_round()

        if r == 1:
            for bid in ct.get_nearby_buildings():
                if ct.get_entity_type(bid) == EntityType.MARKER:
                    self._base_target = ct.get_marker_value(bid)
                    log(f"[BUILDER r1] read marker base_target={self._base_target:x}")
                    break
            return

        if r < 2 or r > NUM_BITS + 1:
            return

        bit_index = r - 2
        pi = bit_index if bit_index <= 1 else bit_index + 1
        target = self._base_target + pi * STRIDE
        probes: list[bytes] = [bytes(SIZE) for _ in range(POOL + 8)]
        addrs = [id(b) for b in probes]
        self.keep.extend(probes)

        bit = 1 if target in addrs else 0
        self._bits.append(bit)
        log(f"[BUILDER r{r}] bit[{bit_index}] target={target:x} bit={bit}")
        log(f"[BUILDER r{r}] addrs={[hex(a) for a in addrs]}")

        if r == NUM_BITS + 1:
            decoded = 0
            for b in self._bits:
                decoded = (decoded << 1) | b
            log(
                f"[BUILDER] decoded={decoded} expected={MESSAGE} {'OK' if decoded == MESSAGE else 'FAIL'}"
            )
