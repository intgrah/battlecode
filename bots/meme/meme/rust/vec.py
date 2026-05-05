from __future__ import annotations

from typing import TYPE_CHECKING

from rust.base import RustStruct, u64

if TYPE_CHECKING:
    from collections.abc import Iterator


class Vec(RustStruct):
    """Vec<i32> layout: cap@0, ptr@8, len@16."""

    cap = u64(0)
    ptr = u64(8)
    len = u64(16)

    def __len__(self) -> int:
        return self.len

    def _read(self, addr: int) -> int:
        v = self._raw.read_u32(addr)
        return v - 0x1_0000_0000 if v & 0x8000_0000 else v

    def __getitem__(self, i: int) -> int:
        if i < 0 or i >= self.len:
            raise IndexError(i)
        return self._read(self.ptr + i * 4)

    def __iter__(self) -> Iterator[int]:
        ptr = self.ptr
        for i in range(self.len):
            yield self._read(ptr + i * 4)
