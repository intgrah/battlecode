from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import RustStruct, i32, u64
from rust.tile import Tile

if TYPE_CHECKING:
    from rust.raw_mem import RawMem


class GameMap(RustStruct):
    """
    GameMap (32 B, align 8):

      +0   24  tiles   Vec<Vec<Tile>>
      +24  4   width   i32
      +28  4   height  i32
    """

    _TILES_OFF: Final = 0
    _TILES_PTR_OFF: Final = 8
    _WIDTH_OFF: Final = 24
    _HEIGHT_OFF: Final = 28

    _VEC_STRIDE: Final = 24
    _VEC_PTR_OFF_INNER: Final = 8
    _TILE_SIZE: Final = 28

    _tiles_ptr = u64(_TILES_PTR_OFF)
    width = i32(_WIDTH_OFF)
    height = i32(_HEIGHT_OFF)

    def __init__(
        self, raw: RawMem, addr: int, rec_outer_ptr: int | None = None
    ) -> None:
        super().__init__(raw, addr)
        self._rec_outer_ptr: Final = rec_outer_ptr

    def tile(self, x: int, y: int) -> Tile:
        outer = self._tiles_ptr
        row_ptr = self._raw.read_u64(
            outer + y * GameMap._VEC_STRIDE + GameMap._VEC_PTR_OFF_INNER
        )
        rec_addr: int | None = None
        if self._rec_outer_ptr is not None:
            rec_row_ptr = self._raw.read_u64(
                self._rec_outer_ptr + y * GameMap._VEC_STRIDE + GameMap._VEC_PTR_OFF_INNER
            )
            rec_addr = rec_row_ptr + x
        return Tile(self._raw, row_ptr + x * GameMap._TILE_SIZE, rec_addr)
