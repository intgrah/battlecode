from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Environment

if TYPE_CHECKING:
    from raw_mem import RawMem

_ENV_FROM_INT: tuple[Environment, ...] = tuple(Environment)
_ENV_TO_INT: dict[Environment, int] = {e: i for i, e in enumerate(_ENV_FROM_INT)}


class Pos:
    """
    Pos { x: i32, y: i32 } stored inline within a Tile at +16.

      +0: x  i32
      +4: y  i32
    """

    def __init__(self, raw: RawMem, addr: int) -> None:
        self._raw = raw
        self._addr = addr

    @property
    def x(self) -> int:
        return self._raw.read_u32(self._addr)

    @x.setter
    def x(self, val: int) -> None:
        self._raw.write_u32(self._addr, val)

    @property
    def y(self) -> int:
        return self._raw.read_u32(self._addr + 4)

    @y.setter
    def y(self, val: int) -> None:
        self._raw.write_u32(self._addr + 4, val)


class Tile:
    """
    Tile struct (sizeof=28, Rust reordered fields — largest-alignment first):

      +0:  building.disc     i32  (0=None, 1=Some)
      +4:  building.val      i32  (entity id if Some, UNINITIALIZED GARBAGE if None)
      +8:  builder_bot.disc  i32
      +12: builder_bot.val   i32  (entity id if Some, garbage if None)
      +16: position.x        i32
      +20: position.y        i32
      +24: environment       u8   (0=Empty,1=Wall,2=TiOre,3=AxOre)
      +25: padding           3 bytes (garbage — do not read as i32 spanning +24)
    """

    def __init__(self, raw: RawMem, addr: int, rec_addr: int | None) -> None:
        self._raw: Final = raw
        self._addr: Final = addr
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
        return _ENV_FROM_INT[self._raw.read_u8(self._addr + 24)]

    @environment.setter
    def environment(self, val: Environment) -> None:
        i = _ENV_TO_INT[val]
        self._raw.write_u8(self._addr + 24, i)
        if self._rec_addr is not None:
            self._raw.write_u8(self._rec_addr, i)


class GameMap:
    """
    GameMap at game_ptr+0:

      +0:  tiles: Vec<Vec<Tile>>  {cap(8), ptr(8), len(8)}  len = map height
      +24: width   i32
      +28: height  i32

    Vec<T> layout: {cap(8), ptr(8), len(8)} — cap-first (Rust stdlib internal order).
    Vec<Tile> row y is at tiles_outer_ptr + y*24; ptr to tile data is at row+8.
    """

    _TILE_SIZE: Final = 28

    def __init__(self, raw: RawMem, addr: int, rec_outer_ptr: int | None) -> None:
        self._raw = raw
        self._addr = addr
        self._rec_outer_ptr = rec_outer_ptr

    @property
    def width(self) -> int:
        return self._raw.read_u32(self._addr + 24)

    @property
    def height(self) -> int:
        return self._raw.read_u32(self._addr + 28)

    def tile(self, x: int, y: int) -> Tile:
        tiles_outer_ptr = self._raw.read_u64(self._addr + 8)
        row_ptr = self._raw.read_u64(tiles_outer_ptr + y * 24 + 8)
        tile_addr = row_ptr + x * GameMap._TILE_SIZE
        rec_addr: int | None = None
        if self._rec_outer_ptr is not None:
            rec_row_ptr = self._raw.read_u64(self._rec_outer_ptr + y * 24 + 8)
            rec_addr = rec_row_ptr + x
        return Tile(self._raw, tile_addr, rec_addr)
