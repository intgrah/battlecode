from __future__ import annotations

import sys
from typing import Final

from cambc import Controller, Environment, Team
from exploit import real_id

_ENV_FROM_INT: tuple[Environment, ...] = tuple(Environment)
_ENV_TO_INT: dict[Environment, int] = {e: i for i, e in enumerate(_ENV_FROM_INT)}
_TEAM_TO_INT: dict[Team, int] = {t: i for i, t in enumerate(Team)}


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
        self._raw = raw
        self._addr = addr
        self._rec_addr = rec_addr

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


class PlayerState:
    """
    PlayerState (sizeof=20):

      +0:  titanium            i32
      +4:  axionite            i32
      +8:  titanium_collected  i32
      +12: axionite_collected  i32
      +16: scale_milli         i32
    """

    def __init__(self, raw: RawMem, addr: int) -> None:
        self._raw = raw
        self._addr = addr

    @property
    def titanium(self) -> int:
        return self._raw.read_u32(self._addr)

    @titanium.setter
    def titanium(self, val: int) -> None:
        self._raw.write_u32(self._addr, val)

    @property
    def axionite(self) -> int:
        return self._raw.read_u32(self._addr + 4)

    @axionite.setter
    def axionite(self, val: int) -> None:
        self._raw.write_u32(self._addr + 4, val)

    @property
    def titanium_collected(self) -> int:
        return self._raw.read_u32(self._addr + 8)

    @titanium_collected.setter
    def titanium_collected(self, val: int) -> None:
        self._raw.write_u32(self._addr + 8, val)

    @property
    def axionite_collected(self) -> int:
        return self._raw.read_u32(self._addr + 12)

    @axionite_collected.setter
    def axionite_collected(self, val: int) -> None:
        self._raw.write_u32(self._addr + 12, val)

    @property
    def scale_milli(self) -> int:
        return self._raw.read_u32(self._addr + 16)

    @scale_milli.setter
    def scale_milli(self, val: int) -> None:
        self._raw.write_u32(self._addr + 16, val)


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


class Game:
    """
    Game struct (Rust reordered fields — largest-alignment first):

      +0:   game_map: GameMap
      +32:  ... (unit_order, entities, harvesters, rng, replay_recorder, edge_last_used)
      +280: players: [PlayerState; 2]  (players[0] at +280, players[1] at +300)
      +320: turn: i32
    """

    _PLAYERS_OFF: Final = 280
    _PLAYER_SIZE: Final = 20
    _TURN_OFF: Final = 320

    @staticmethod
    def open(raw: RawMem, ct: Controller) -> Game:
        """
        Locate the Rust Game struct via the Controller's pyo3 object layout.

        Controller (pyo3 #[pyclass], no dict/weakref):
          +0:  ob_refcnt
          +8:  ob_type
          +16: game: Rc<RefCell<Game>>  ← pointer to RcBox

        RcBox<RefCell<Game>> at ct_ptr:
          +0:  strong count
          +8:  weak count
          +16: borrow flag (isize, from RefCell)
          +24: Game struct  ← game_ptr = ct_ptr + 24
        """
        h = ct.get_map_height()

        ct_ptr = raw.read_u64(real_id(ct) + 16)
        game_ptr = ct_ptr + 24

        # Scan for replay_recorder.environment: a second Vec<Vec<T>> with outer.len == h.
        # game_map.tiles is at +0 (skip it). Safe: only reads game_ptr + small offsets.
        rec_outer_ptr: int | None = None
        for off in range(8, 280, 8):
            if raw.read_u64(game_ptr + off) != h:
                continue
            vec_start = off - 16
            if vec_start <= 0:
                continue
            cap = raw.read_u64(game_ptr + vec_start)
            ptr = raw.read_u64(game_ptr + vec_start + 8)
            if cap >= h and 0x1000_0000_0000 <= ptr <= 0x0000_FFFF_FFFF_FFFF:
                rec_outer_ptr = raw.read_u64(game_ptr + vec_start + 8)
                break

        return Game(raw, game_ptr, rec_outer_ptr)

    def __init__(self, raw: RawMem, game_ptr: int, rec_outer_ptr: int | None) -> None:
        self._raw = raw
        self._game_ptr = game_ptr
        self._rec_outer_ptr = rec_outer_ptr

    @property
    def game_map(self) -> GameMap:
        return GameMap(self._raw, self._game_ptr, self._rec_outer_ptr)

    def player(self, team: Team) -> PlayerState:
        return PlayerState(
            self._raw,
            self._game_ptr + Game._PLAYERS_OFF + _TEAM_TO_INT[team] * Game._PLAYER_SIZE,
        )

    @property
    def turn(self) -> int:
        return self._raw.read_u32(self._game_ptr + Game._TURN_OFF)

    @turn.setter
    def turn(self, val: int) -> None:
        self._raw.write_u32(self._game_ptr + Game._TURN_OFF, val)
