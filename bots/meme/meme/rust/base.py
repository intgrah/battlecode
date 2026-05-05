from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from rust.raw_mem import RawMem


class RustStruct:
    __slots__ = ("_addr", "_raw")

    def __init__(self, raw: RawMem, addr: int) -> None:
        self._raw: Final = raw
        self._addr: Final = addr


class u8:  # noqa: N801
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        return obj._raw.read_u8(obj._addr + self._off)

    def __set__(self, obj: RustStruct, val: int) -> None:
        obj._raw.write_u8(obj._addr + self._off, val & 0xFF)


class u32:  # noqa: N801
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        return obj._raw.read_u32(obj._addr + self._off)

    def __set__(self, obj: RustStruct, val: int) -> None:
        obj._raw.write_u32(obj._addr + self._off, val & 0xFFFF_FFFF)


class i32:  # noqa: N801
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        v = obj._raw.read_u32(obj._addr + self._off)
        return v - 0x1_0000_0000 if v & 0x8000_0000 else v

    def __set__(self, obj: RustStruct, val: int) -> None:
        obj._raw.write_u32(obj._addr + self._off, val & 0xFFFF_FFFF)


class u64:  # noqa: N801
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        return obj._raw.read_u64(obj._addr + self._off)


class enum_u8[E: Enum]:  # noqa: N801
    """1-byte field decoded as a Python enum via a tag→variant table."""

    __slots__ = ("_off", "_table", "_to_int")

    def __init__(self, off: int, table: tuple[E, ...]) -> None:
        self._off: Final = off
        self._table: Final = table
        self._to_int: Final = {v: i for i, v in enumerate(table)}

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> E:
        return self._table[obj._raw.read_u8(obj._addr + self._off)]

    def __set__(self, obj: RustStruct, val: E) -> None:
        obj._raw.write_u8(obj._addr + self._off, self._to_int[val])
