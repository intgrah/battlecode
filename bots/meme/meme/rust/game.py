from __future__ import annotations

from typing import Final

from cambc import Controller, Position, Team

from rust.base import RustStruct, i32, read_position, u64
from rust.entity import Entity
from rust.game_map import GameMap
from rust.hashmap import HashMap
from rust.player_state import PlayerState
from rust.raw_mem import RawMem
from rust.vec import Vec

_TEAM_TO_INT: dict[Team, int] = {t: i for i, t in enumerate(Team)}

_POSITION_SIZE: Final = 8


def _read_i32(raw: RawMem, addr: int) -> int:
    v = raw.read_u32(addr)
    return v - 0x1_0000_0000 if v & 0x8000_0000 else v


def _read_position_pair(raw: RawMem, addr: int) -> tuple[Position, Position]:
    return read_position(raw, addr), read_position(raw, addr + _POSITION_SIZE)


# (Position, Position) is 16 B, value i32 is 4 B + 4 B pad = 20 B per bucket.
_EDGE_KEY_SIZE: Final = 2 * _POSITION_SIZE
_EDGE_VALUE_OFF: Final = _EDGE_KEY_SIZE
_EDGE_SLOT_SIZE: Final = 20


class Game(RustStruct):
    """
    Game (640 B, align 8):

      +0    32   game_map         GameMap
      +32   24   unit_order       Vec<i32>
      +56   24   harvesters       Vec<i32>
      +80   80   replay_recorder  ReplayRecorder
      +160  24   resign_message   Option<String>
      +184  48   entities         HashMap<i32, Entity>
      +232  48   edge_last_used   HashMap<(Pos, Pos), i32>
      +280  40   players          [PlayerState; 2]
      +320  312  rng              StdRng (ChaCha12Rng)
      +632  4    turn             i32
      +636  4    next_id          i32
    """

    _GAME_MAP_OFF: Final = 0
    _UNIT_ORDER_OFF: Final = 32
    _HARVESTERS_OFF: Final = 56
    _RESIGN_MESSAGE_OFF: Final = 160
    _RESIGN_CAP_OFF: Final = _RESIGN_MESSAGE_OFF
    _RESIGN_PTR_OFF: Final = _RESIGN_MESSAGE_OFF + 8
    _RESIGN_LEN_OFF: Final = _RESIGN_MESSAGE_OFF + 16
    _ENTITIES_OFF: Final = 184
    _EDGE_LAST_USED_OFF: Final = 232
    _PLAYERS_OFF: Final = 280
    _PLAYER_SIZE: Final = 20
    _TURN_OFF: Final = 632
    _NEXT_ID_OFF: Final = 636

    _CTRL_PTR_OFFSET_IN_CT: Final = 16
    _GAME_OFFSET_IN_CT: Final = 24

    turn = i32(_TURN_OFF)
    next_id = i32(_NEXT_ID_OFF)
    _resign_cap = u64(_RESIGN_CAP_OFF)
    _resign_ptr = u64(_RESIGN_PTR_OFF)
    _resign_len = u64(_RESIGN_LEN_OFF)

    @staticmethod
    def open(raw: RawMem, ct: Controller) -> Game:
        ct_ptr = raw.read_u64(RawMem.id(ct) + Game._CTRL_PTR_OFFSET_IN_CT)
        return Game(raw, ct_ptr + Game._GAME_OFFSET_IN_CT)

    @property
    def game_map(self) -> GameMap:
        return GameMap(self._raw, self._addr + Game._GAME_MAP_OFF)

    def player(self, team: Team) -> PlayerState:
        return PlayerState(
            self._raw,
            self._addr + Game._PLAYERS_OFF + _TEAM_TO_INT[team] * Game._PLAYER_SIZE,
        )

    @property
    def resign_message(self) -> str | None:
        if self._resign_cap >> 63:
            return None
        return self._raw.read_bytes(self._resign_ptr, self._resign_len).decode(
            "utf-8", errors="replace"
        )

    @property
    def unit_order(self) -> Vec:
        return Vec(self._raw, self._addr + Game._UNIT_ORDER_OFF)

    @property
    def harvesters(self) -> Vec:
        return Vec(self._raw, self._addr + Game._HARVESTERS_OFF)

    @property
    def entities(self) -> HashMap[int, Entity]:
        return HashMap(
            self._raw,
            self._addr + Game._ENTITIES_OFF,
            slot_size=Entity.SLOT_SIZE,
            key=RawMem.read_u32,
            value=Entity,
        )

    @property
    def edge_last_used(self) -> HashMap[tuple[Position, Position], int]:
        return HashMap(
            self._raw,
            self._addr + Game._EDGE_LAST_USED_OFF,
            slot_size=_EDGE_SLOT_SIZE,
            key=_read_position_pair,
            value=lambda raw, s: _read_i32(raw, s + _EDGE_VALUE_OFF),
        )
