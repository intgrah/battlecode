from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Environment

from rust.base import RustStruct, position, u8

if TYPE_CHECKING:
    from rust.raw_mem import RawMem

_ENV_FROM_INT: tuple[Environment, ...] = tuple(Environment)
_ENV_TO_INT: dict[Environment, int] = {e: i for i, e in enumerate(_ENV_FROM_INT)}


class Tile(RustStruct):
    """
    Tile (28 B, align 4):

      +0   8  building     Option<i32>   (disc@+0, val@+4)
      +8   8  builder_bot  Option<i32>   (disc@+8, val@+12)
      +16  8  position     Pos
      +24  1  environment  Environment
    """

    _BUILDING_DISC_OFF: Final = 0
    _BUILDING_VAL_OFF: Final = 4
    _BUILDER_BOT_DISC_OFF: Final = 8
    _BUILDER_BOT_VAL_OFF: Final = 12
    _POSITION_OFF: Final = 16
    _ENVIRONMENT_OFF: Final = 24

    position = position(_POSITION_OFF)
    _env_byte = u8(_ENVIRONMENT_OFF)

    def __init__(self, raw: RawMem, addr: int, rec_addr: int | None = None) -> None:
        super().__init__(raw, addr)
        self._rec_addr: Final = rec_addr

    @property
    def building(self) -> int | None:
        if not self._raw.read_u32(self._addr + Tile._BUILDING_DISC_OFF):
            return None
        return self._raw.read_u32(self._addr + Tile._BUILDING_VAL_OFF)

    @building.setter
    def building(self, val: int | None) -> None:
        if val is None:
            self._raw.write_u32(self._addr + Tile._BUILDING_DISC_OFF, 0)
        else:
            self._raw.write_u32(self._addr + Tile._BUILDING_DISC_OFF, 1)
            self._raw.write_u32(self._addr + Tile._BUILDING_VAL_OFF, val)

    @property
    def builder_bot(self) -> int | None:
        if not self._raw.read_u32(self._addr + Tile._BUILDER_BOT_DISC_OFF):
            return None
        return self._raw.read_u32(self._addr + Tile._BUILDER_BOT_VAL_OFF)

    @builder_bot.setter
    def builder_bot(self, val: int | None) -> None:
        if val is None:
            self._raw.write_u32(self._addr + Tile._BUILDER_BOT_DISC_OFF, 0)
        else:
            self._raw.write_u32(self._addr + Tile._BUILDER_BOT_DISC_OFF, 1)
            self._raw.write_u32(self._addr + Tile._BUILDER_BOT_VAL_OFF, val)

    @property
    def environment(self) -> Environment:
        return _ENV_FROM_INT[self._env_byte]

    @environment.setter
    def environment(self, val: Environment) -> None:
        i = _ENV_TO_INT[val]
        self._env_byte = i
        if self._rec_addr is not None:
            self._raw.write_u8(self._rec_addr, i)
