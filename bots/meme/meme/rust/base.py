# ruff: noqa: N801
# Lowercase class names are intentional.
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Final

from cambc import Position

if TYPE_CHECKING:
    from rust.raw_mem import RawMem


def _read_i32(raw: RawMem, addr: int) -> int:
    v = raw.read_u32(addr)
    return v - 0x1_0000_0000 if v & 0x8000_0000 else v


def read_position(raw: RawMem, addr: int) -> Position:
    """Decode 8 bytes (i32 x, i32 y) starting at `addr` into a `Position`."""
    return Position(_read_i32(raw, addr), _read_i32(raw, addr + 4))


def write_position(raw: RawMem, addr: int, val: Position) -> None:
    """Encode `Position` as 8 bytes (i32 x, i32 y) starting at `addr`."""
    raw.write_u32(addr, val.x & 0xFFFF_FFFF)
    raw.write_u32(addr + 4, val.y & 0xFFFF_FFFF)


class RustStruct:
    __slots__ = ("_addr", "_raw")

    def __init__(self, raw: RawMem, addr: int) -> None:
        self._raw: Final = raw
        self._addr: Final = addr


class u8:
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        return obj._raw.read_u8(obj._addr + self._off)

    def __set__(self, obj: RustStruct, val: int) -> None:
        obj._raw.write_u8(obj._addr + self._off, val & 0xFF)


class u32:
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        return obj._raw.read_u32(obj._addr + self._off)

    def __set__(self, obj: RustStruct, val: int) -> None:
        obj._raw.write_u32(obj._addr + self._off, val & 0xFFFF_FFFF)


class i32:
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        v = obj._raw.read_u32(obj._addr + self._off)
        return v - 0x1_0000_0000 if v & 0x8000_0000 else v

    def __set__(self, obj: RustStruct, val: int) -> None:
        obj._raw.write_u32(obj._addr + self._off, val & 0xFFFF_FFFF)


class u64:
    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> int:
        return obj._raw.read_u64(obj._addr + self._off)


class enum_u8[E: Enum]:
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


class option[E: Enum]:
    """1-byte niche-encoded Option<E>. None ↔ raw byte == `niche`."""

    __slots__ = ("_niche", "_off", "_table", "_to_int")

    def __init__(self, off: int, table: tuple[E, ...], *, niche: int) -> None:
        self._off: Final = off
        self._table: Final = table
        self._niche: Final = niche
        self._to_int: Final = {v: i for i, v in enumerate(table)}

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> E | None:
        b = obj._raw.read_u8(obj._addr + self._off)
        return None if b == self._niche else self._table[b]

    def __set__(self, obj: RustStruct, val: E | None) -> None:
        b = self._niche if val is None else self._to_int[val]
        obj._raw.write_u8(obj._addr + self._off, b)


class position:
    """8-byte (i32 x, i32 y) field decoded as a `cambc.Position`."""

    __slots__ = ("_off",)

    def __init__(self, off: int) -> None:
        self._off: Final = off

    def __get__(self, obj: RustStruct, _: type[RustStruct] | None = None) -> Position:
        return read_position(obj._raw, obj._addr + self._off)

    def __set__(self, obj: RustStruct, val: Position) -> None:
        write_position(obj._raw, obj._addr + self._off, val)
