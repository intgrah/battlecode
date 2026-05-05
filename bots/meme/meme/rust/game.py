from __future__ import annotations

from typing import Final

from cambc import Controller, Team

from rust.base import RustStruct, i32, u64
from rust.entity import Entity
from rust.game_map import GameMap
from rust.hashmap import HashMap
from rust.player_state import PlayerState
from rust.raw_mem import RawMem
from rust.vec import Vec

_TEAM_TO_INT: dict[Team, int] = {t: i for i, t in enumerate(Team)}


class Game(RustStruct):
    """
    Game (640 B, std HashMap):
      +0   game_map        GameMap (32)
      +32  unit_order      Vec<i32> (24)
      +56  harvesters      Vec<i32> (24)
      +80  replay_recorder ReplayRecorder (80)
      +160 resign_message  Option<String> (24)
      +184 entities        HashMap<i32, Entity> (48)
      +232 edge_last_used  HashMap<(Pos,Pos), i32> (48)
      +280 players         [PlayerState; 2] (40)
      +320 rng             StdRng (312)
      +632 turn            i32
      +636 next_id         i32
    """

    turn = i32(632)
    next_id = i32(636)
    _resign_cap = u64(160)
    _resign_ptr = u64(168)
    _resign_len = u64(176)

    _PLAYER_SIZE: Final = 20

    @staticmethod
    def open(raw: RawMem, ct: Controller) -> Game:
        ct_ptr = raw.read_u64(RawMem.id(ct) + 16)
        return Game(raw, ct_ptr + 24)

    @property
    def game_map(self) -> GameMap:
        return GameMap(self._raw, self._addr)

    def player(self, team: Team) -> PlayerState:
        return PlayerState(
            self._raw, self._addr + 280 + _TEAM_TO_INT[team] * Game._PLAYER_SIZE
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
        return Vec(self._raw, self._addr + 32)

    @property
    def harvesters(self) -> Vec:
        return Vec(self._raw, self._addr + 56)

    @property
    def entities(self) -> HashMap:
        return HashMap(
            self._raw, self._addr + 184, slot_size=Entity.SLOT_SIZE, key_size=4
        )

    @property
    def edge_last_used(self) -> HashMap:
        return HashMap(self._raw, self._addr + 232, slot_size=20, key_size=16)
