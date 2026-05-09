"""Replace every tile's terrain with `Environment.EMPTY` in C-speed bulk.

Clears BOTH the game-map tiles (28 B each, env byte at +24, step=28) AND
the replay recorder's initial-environment grid (1 B each, contiguous).
Without the recorder wipe the replay viewer still shows the original terrain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rust import Game

_VEC_STRIDE = 24
_VEC_PTR_OFF = 8
_TILE_SIZE = 28
_ENV_OFFSET = 24
_REC_ENV_OFF = 0


def wipe_map(g: Game) -> None:
    raw = g._raw
    mem = raw._mem
    h = g.game_map.height
    w = g.game_map.width
    zeros = b"\x00" * w

    tile_outer = g.game_map._tiles_ptr
    rec_outer = raw.read_u64(g.replay_recorder._addr + _REC_ENV_OFF + _VEC_PTR_OFF)
    row_stride = w * _TILE_SIZE

    for i in range(h):
        tile_row_ptr = raw.read_u64(tile_outer + i * _VEC_STRIDE + _VEC_PTR_OFF)
        start = tile_row_ptr + _ENV_OFFSET
        mem[start : start + row_stride : _TILE_SIZE] = zeros

        rec_row_ptr = raw.read_u64(rec_outer + i * _VEC_STRIDE + _VEC_PTR_OFF)
        mem[rec_row_ptr : rec_row_ptr + w] = zeros
