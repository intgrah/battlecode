from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import U64, RustStruct

if TYPE_CHECKING:
    from collections.abc import Iterator


class Vec(RustStruct):
    """
    Vec<i32> (24 B, align 8):

      +0   8  cap  usize
      +8   8  ptr  *T
      +16  8  len  usize
    """

    _CAP_OFF: Final = 0
    _PTR_OFF: Final = 8
    _LEN_OFF: Final = 16
    _ELEM_SIZE: Final = 4

    cap = U64(_CAP_OFF)
    ptr = U64(_PTR_OFF)
    len = U64(_LEN_OFF)

    def __len__(self) -> int:
        return self.len

    def _read(self, addr: int) -> int:
        v = self._raw.read_u32(addr)
        return v - 0x1_0000_0000 if v & 0x8000_0000 else v

    def __getitem__(self, i: int) -> int:
        if i < 0 or i >= self.len:
            raise IndexError(i)
        return self._read(self.ptr + i * Vec._ELEM_SIZE)

    def __setitem__(self, i: int, v: int) -> None:
        if i < 0 or i >= self.len:
            raise IndexError(i)
        self._raw.write_u32(self.ptr + i * Vec._ELEM_SIZE, v)

    def __iter__(self) -> Iterator[int]:
        ptr = self.ptr
        for i in range(self.len):
            yield self._read(ptr + i * Vec._ELEM_SIZE)

    def __reversed__(self) -> Iterator[int]:
        ptr = self.ptr
        for i in range(self.len - 1, -1, -1):
            yield self._read(ptr + i * Vec._ELEM_SIZE)
