from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Environment

from rust.base import RustStruct, u8
from rust.pos import Pos

if TYPE_CHECKING:
    from rust.raw_mem import RawMem

_ENV_FROM_INT: tuple[Environment, ...] = tuple(Environment)
_ENV_TO_INT: dict[Environment, int] = {e: i for i, e in enumerate(_ENV_FROM_INT)}


class Tile(RustStruct):
    """
    Tile (28 B):
      +0  building.disc i32     (0=None, 1=Some)
      +4  building.val  i32     (id when Some)
      +8  builder_bot.disc i32
      +12 builder_bot.val  i32
      +16 position.x i32
      +20 position.y i32
      +24 environment u8
    """

    _env_byte = u8(24)

    def __init__(self, raw: RawMem, addr: int, rec_addr: int | None = None) -> None:
        super().__init__(raw, addr)
        self._rec_addr: Final = rec_addr

    @property
    def building(self) -> int | None:
        return (
            self._raw.read_u32(self._addr + 4)
            if self._raw.read_u32(self._addr)
            else None
        )

    @building.setter
    def building(self, val: int | None) -> None:
        if val is None:
            self._raw.write_u32(self._addr, 0)
        else:
            self._raw.write_u32(self._addr, 1)
            self._raw.write_u32(self._addr + 4, val)

    @property
    def builder_bot(self) -> int | None:
        return (
            self._raw.read_u32(self._addr + 12)
            if self._raw.read_u32(self._addr + 8)
            else None
        )

    @builder_bot.setter
    def builder_bot(self, val: int | None) -> None:
        if val is None:
            self._raw.write_u32(self._addr + 8, 0)
        else:
            self._raw.write_u32(self._addr + 8, 1)
            self._raw.write_u32(self._addr + 12, val)

    @property
    def position(self) -> Pos:
        return Pos(self._raw, self._addr + 16)

    @property
    def environment(self) -> Environment:
        return _ENV_FROM_INT[self._env_byte]

    @environment.setter
    def environment(self, val: Environment) -> None:
        i = _ENV_TO_INT[val]
        self._env_byte = i
        if self._rec_addr is not None:
            self._raw.write_u8(self._rec_addr, i)
