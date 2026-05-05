from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import RustStruct, i32, u64
from rust.tile import Tile

if TYPE_CHECKING:
    from rust.raw_mem import RawMem


class GameMap(RustStruct):
    """
    GameMap (32 B):
      +0  tiles: Vec<Vec<Tile>>  (cap, ptr, len; len = height)
      +24 width  i32
      +28 height i32
    """

    _tiles_ptr = u64(8)
    width = i32(24)
    height = i32(28)
    _TILE_SIZE: Final = 28

    def __init__(
        self, raw: RawMem, addr: int, rec_outer_ptr: int | None = None
    ) -> None:
        super().__init__(raw, addr)
        self._rec_outer_ptr: Final = rec_outer_ptr

    def tile(self, x: int, y: int) -> Tile:
        outer = self._tiles_ptr
        row_ptr = self._raw.read_u64(outer + y * 24 + 8)
        rec_addr: int | None = None
        if self._rec_outer_ptr is not None:
            rec_row_ptr = self._raw.read_u64(self._rec_outer_ptr + y * 24 + 8)
            rec_addr = rec_row_ptr + x
        return Tile(self._raw, row_ptr + x * GameMap._TILE_SIZE, rec_addr)
