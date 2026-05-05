from __future__ import annotations

from typing import Final

from cambc import Controller, Team
from game_map import GameMap
from raw_mem import RawMem
from rust_types import Entity, HashMap, Vec

_TEAM_TO_INT: dict[Team, int] = {t: i for i, t in enumerate(Team)}


class PlayerState:
    """
    PlayerState (sizeof=20):

      +0:  titanium            i32
      +4:  axionite            i32
      +8:  titanium_collected  i32
      +12: axionite_collected  i32
      +16: scale_milli         i32
    """

    _TITANIUM_OFF: Final = 0
    _AXIONITE_OFF: Final = 4
    _TITANIUM_COLLECTED_OFF: Final = 8
    _AXIONITE_COLLECTED_OFF: Final = 12
    _SCALE_MILLI_OFF: Final = 16

    def __init__(self, raw: RawMem, addr: int) -> None:
        self._raw: Final = raw
        self._addr: Final = addr

    @property
    def titanium(self) -> int:
        return self._raw.read_u32(self._addr + PlayerState._TITANIUM_OFF)

    @titanium.setter
    def titanium(self, val: int) -> None:
        self._raw.write_u32(self._addr + PlayerState._TITANIUM_OFF, val)

    @property
    def axionite(self) -> int:
        return self._raw.read_u32(self._addr + PlayerState._AXIONITE_OFF)

    @axionite.setter
    def axionite(self, val: int) -> None:
        self._raw.write_u32(self._addr + PlayerState._AXIONITE_OFF, val)

    @property
    def titanium_collected(self) -> int:
        return self._raw.read_u32(self._addr + PlayerState._TITANIUM_COLLECTED_OFF)

    @titanium_collected.setter
    def titanium_collected(self, val: int) -> None:
        self._raw.write_u32(self._addr + PlayerState._TITANIUM_COLLECTED_OFF, val)

    @property
    def axionite_collected(self) -> int:
        return self._raw.read_u32(self._addr + PlayerState._AXIONITE_COLLECTED_OFF)

    @axionite_collected.setter
    def axionite_collected(self, val: int) -> None:
        self._raw.write_u32(self._addr + PlayerState._AXIONITE_COLLECTED_OFF, val)

    @property
    def scale_milli(self) -> int:
        return self._raw.read_u32(self._addr + PlayerState._SCALE_MILLI_OFF)

    @scale_milli.setter
    def scale_milli(self, val: int) -> None:
        self._raw.write_u32(self._addr + PlayerState._SCALE_MILLI_OFF, val)


class Game:
    """
    Game struct (server engine uses HashMap, not FxHashMap — each map is 48 bytes):

      +0x000 (  0): game_map:        GameMap               (32)  [confirmed]
      +0x020 ( 32): unit_order:      Vec<i32>              (24)  [confirmed]
      +0x038 ( 56): harvesters:      Vec<i32>              (24)  [confirmed]
      +0x050 ( 80): replay_recorder: ReplayRecorder        (80)  [confirmed]
      +0x0a0 (160): resign_message:  Option<String>        (24)  [confirmed]
      +0x0b8 (184): entities:        HashMap<i32, Entity>  (48)  [confirmed]
      +0x0e8 (232): edge_last_used:  HashMap<(Pos,Pos),i32>(48)  [confirmed]
      +0x118 (280): players:         [PlayerState; 2]      (40)  [confirmed]
      +0x140 (320): rng:             StdRng (ChaCha12Rng)  (312) [confirmed]
      +0x278 (632): turn:            i32                   (4)   [confirmed]
      +0x27c (636): next_id:         i32                   (4)   [confirmed]
      +0x280 (640): ...additional fields observed to ~0x2d8
    """

    _GAME_MAP_OFF: Final = 0
    _UNIT_ORDER_OFF: Final = 32
    _HARVESTERS_OFF: Final = 56
    _REPLAY_RECORDER_OFF: Final = 80
    _RESIGN_MESSAGE_OFF: Final = 160
    _ENTITIES_OFF: Final = 184
    _EDGE_LAST_USED_OFF: Final = 232
    _PLAYERS_OFF: Final = 280
    _PLAYER_SIZE: Final = 20
    _RNG_OFF: Final = 320
    _TURN_OFF: Final = 632
    _NEXT_ID_OFF: Final = 636

    @staticmethod
    def open(raw: RawMem, ct: Controller) -> Game:
        ct_ptr = raw.read_u64(RawMem.id(ct) + 16)
        game_ptr = ct_ptr + 24
        return Game(raw, game_ptr)

    def __init__(self, raw: RawMem, game_ptr: int) -> None:
        self._raw: Final = raw
        self._game_ptr: Final = game_ptr

    @property
    def game_map(self) -> GameMap:
        return GameMap(self._raw, self._game_ptr + Game._GAME_MAP_OFF, None)

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

    @property
    def next_id(self) -> int:
        return self._raw.read_u32(self._game_ptr + Game._NEXT_ID_OFF)

    @next_id.setter
    def next_id(self, val: int) -> None:
        self._raw.write_u32(self._game_ptr + Game._NEXT_ID_OFF, val)

    @property
    def resign_message(self) -> str | None:
        cap = self._raw.read_u64(self._game_ptr + Game._RESIGN_MESSAGE_OFF)
        if cap >> 63:
            return None
        ptr = self._raw.read_u64(self._game_ptr + Game._RESIGN_MESSAGE_OFF + 8)
        length = self._raw.read_u64(self._game_ptr + Game._RESIGN_MESSAGE_OFF + 16)
        return self._raw.read_bytes(ptr, length).decode("utf-8", errors="replace")

    @property
    def unit_order(self) -> Vec:
        return Vec(self._raw, self._game_ptr + Game._UNIT_ORDER_OFF, 4)

    @property
    def harvesters(self) -> Vec:
        return Vec(self._raw, self._game_ptr + Game._HARVESTERS_OFF, 4)

    @property
    def entities(self) -> HashMap:
        return HashMap(
            self._raw,
            self._game_ptr + Game._ENTITIES_OFF,
            slot_size=Entity.SLOT_SIZE,
            key_size=4,
        )

    @property
    def edge_last_used(self) -> HashMap:
        return HashMap(
            self._raw,
            self._game_ptr + Game._EDGE_LAST_USED_OFF,
            slot_size=20,
            key_size=16,
        )
