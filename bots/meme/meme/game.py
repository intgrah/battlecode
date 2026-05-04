import sys
from collections.abc import Callable

from cambc import Controller
from exploit import real_id

# =============================================================================
# Memory layout findings (CPython 3.12, aarch64, Rust release build)
# If the Rust compiler changes struct layout, re-derive these offsets.
#
# Controller (pyo3 #[pyclass], no dict/weakref):
#   +0:  ob_refcnt (CPython)
#   +8:  ob_type   (CPython)
#   +16: game: Rc<RefCell<Game>>  ← pointer to RcBox
#
# RcBox<RefCell<Game>> at rc_ptr:
#   +0:  strong count (usize)
#   +8:  weak count   (usize)
#   +16: borrow flag  (isize, from RefCell)
#   +24: Game struct  ← game_ptr = rc_ptr + 24
#
# Game struct (Rust reordered fields — largest-alignment first):
#   +0:  game_map: GameMap
#          +0  tiles: Vec<Vec<Tile>>  {cap(8), ptr(8), len(8)}
#                 len  = map height
#                 ptr  → array of Vec<Tile>, one per row
#          +24 width:  i32
#          +28 height: i32
#   +32: (next field — Vec with len=2, likely unit_order: Vec<i32>)
#   ...
#   +280: players: [PlayerState; 2]
#           each PlayerState = {titanium(4), axionite(4), titanium_collected(4),
#                               axionite_collected(4), scale_milli(4)} = 20 bytes
#           players[0] at +280, players[1] at +300
#   +320: turn: i32
#
# Vec<T> layout (all observed Vecs):  {cap(8), ptr(8), len(8)}
# NOTE: this is cap-first, contrary to the Rust source order of Vec (which is
# ptr, cap, len in std). Recheck if Rust stdlib changes Vec internals.
#
# Vec<Tile> row y: stored at tiles_outer_ptr + y * 24
#   cap at +0, ptr (→ tile data) at +8, len (= map width) at +16
#
# Tile struct (sizeof=28, Rust reordered fields):
#   +0:  building.disc     i32  (0=None, 1=Some)
#   +4:  building.val      i32  (entity id if Some, UNINITIALIZED GARBAGE if None)
#   +8:  builder_bot.disc  i32
#   +12: builder_bot.val   i32  (entity id if Some, garbage if None)
#   +16: position.x        i32
#   +20: position.y        i32
#   +24: environment       u8   (0=Empty,1=Wall,2=TiOre,3=AxOre)
#   +25: padding           3 bytes (garbage — do not read as i32 spanning +24)
# =============================================================================

_TILE_SIZE: int = 28
_TILE_ENV_OFF: int = 24
_PLAYERS_OFF: int = 280
_PLAYER_SIZE: int = 20
_TURN_OFF: int = 320


class RawMem:
    def __init__(self, mem: bytearray, anchor: bytearray) -> None:
        self._mem = mem
        self._anchor = anchor

    def read_u8(self, addr: int) -> int:
        return self._mem[addr]

    def read_u32(self, addr: int) -> int:
        return int.from_bytes(self._mem[addr : addr + 4], sys.byteorder)

    def read_u64(self, addr: int) -> int:
        return int.from_bytes(self._mem[addr : addr + 8], sys.byteorder)

    def write_u8(self, addr: int, val: int) -> None:
        self._mem[addr] = val

    def write_u32(self, addr: int, val: int) -> None:
        self._mem[addr : addr + 4] = (val & 0xFFFF_FFFF).to_bytes(4, sys.byteorder)


class Game:
    def __init__(
        self,
        raw: RawMem,
        w: int,
        h: int,
        game_ptr: int,
        tiles_outer_ptr: int,
        rec_outer_ptr: int | None,
    ) -> None:
        self._raw = raw
        self.w = w
        self.h = h
        self._game_ptr = game_ptr
        self._tiles_outer_ptr = tiles_outer_ptr
        self._rec_outer_ptr = rec_outer_ptr

    def _tile_ptr(self, x: int, y: int) -> int:
        row_ptr = self._raw.read_u64(self._tiles_outer_ptr + y * 24 + 8)
        return row_ptr + x * _TILE_SIZE

    def _player_base(self, team: int) -> int:
        return self._game_ptr + _PLAYERS_OFF + team * _PLAYER_SIZE

    @property
    def turn(self) -> int:
        return self._raw.read_u32(self._game_ptr + _TURN_OFF)

    def read_env(self, x: int, y: int) -> int:
        return self._raw.read_u8(self._tile_ptr(x, y) + _TILE_ENV_OFF)

    def write_env(self, x: int, y: int, env: int) -> None:
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        self._raw.write_u8(self._tile_ptr(x, y) + _TILE_ENV_OFF, env)
        if self._rec_outer_ptr is not None:
            rec_row_ptr = self._raw.read_u64(self._rec_outer_ptr + y * 24 + 8)
            self._raw.write_u8(rec_row_ptr + x, env)

    def tile_building(self, x: int, y: int) -> int | None:
        tp = self._tile_ptr(x, y)
        return self._raw.read_u32(tp + 4) if self._raw.read_u32(tp) else None

    def tile_bot(self, x: int, y: int) -> int | None:
        tp = self._tile_ptr(x, y)
        return self._raw.read_u32(tp + 12) if self._raw.read_u32(tp + 8) else None

    def titanium(self, team: int) -> int:
        return self._raw.read_u32(self._player_base(team))

    def axionite(self, team: int) -> int:
        return self._raw.read_u32(self._player_base(team) + 4)

    def titanium_collected(self, team: int) -> int:
        return self._raw.read_u32(self._player_base(team) + 8)

    def axionite_collected(self, team: int) -> int:
        return self._raw.read_u32(self._player_base(team) + 12)

    def scale_milli(self, team: int) -> int:
        return self._raw.read_u32(self._player_base(team) + 16)

    def set_titanium(self, team: int, val: int) -> None:
        self._raw.write_u32(self._player_base(team), val)

    def set_axionite(self, team: int, val: int) -> None:
        self._raw.write_u32(self._player_base(team) + 4, val)

    def set_titanium_collected(self, team: int, val: int) -> None:
        self._raw.write_u32(self._player_base(team) + 8, val)

    def set_axionite_collected(self, team: int, val: int) -> None:
        self._raw.write_u32(self._player_base(team) + 12, val)


def _find_env_recorder_offset(
    game_ptr: int, read_u64: Callable[[int], int], h: int
) -> int | None:
    # Scan game struct for a second Vec<Vec<T>> with outer.len == h.
    # game_map.tiles is at +0 (skip it). replay_recorder.environment is the
    # only other outer Vec in Game with len == map height.
    # Safe to scan: we only read from game_ptr + small_offsets (all mapped).
    for off in range(8, 280, 8):
        if read_u64(game_ptr + off) != h:
            continue
        vec_start = off - 16
        if vec_start < 0:
            continue
        if vec_start == 0:
            continue  # that's game_map.tiles
        cap = read_u64(game_ptr + vec_start)
        ptr = read_u64(game_ptr + vec_start + 8)
        if cap >= h and 0x1000_0000_0000 <= ptr <= 0x0000_FFFF_FFFF_FFFF:
            return vec_start
    return None


def open_game(mem: bytearray, anchor: bytearray, ct: Controller) -> Game:
    raw = RawMem(mem, anchor)

    def read_u64(addr: int) -> int:
        return int.from_bytes(mem[addr : addr + 8], sys.byteorder)

    w = ct.get_map_width()
    h = ct.get_map_height()

    rc_ptr = read_u64(real_id(ct) + 16)
    game_ptr = rc_ptr + 24

    tiles_outer_ptr = read_u64(game_ptr + 8)
    rec_off = _find_env_recorder_offset(game_ptr, read_u64, h)
    rec_outer_ptr = read_u64(game_ptr + rec_off + 8) if rec_off is not None else None
    return Game(raw, w, h, game_ptr, tiles_outer_ptr, rec_outer_ptr)
