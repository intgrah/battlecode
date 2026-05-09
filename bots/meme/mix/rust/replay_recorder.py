from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import U8, U64, Inner, RustStruct
from rust.game_diff import _TAG_FIRE_TURRET, _TAG_MOVE_BUILDER_BOT, GameDiff
from rust.tile import _ENV_FROM_INT, _ENV_TO_INT

if TYPE_CHECKING:
    from collections.abc import Iterator

    from cambc import Environment

    from rust.raw_mem import RawMem


_VEC_SIZE: Final = 24
_VEC_CAP_OFF: Final = 0
_VEC_PTR_OFF: Final = 8
_VEC_LEN_OFF: Final = 16


class EnvRow(RustStruct):
    """
    `Vec<Environment>` (24 B): one row, indexed by x, typed as `Environment`.

      +0   8  cap  usize
      +8   8  ptr  *u8
      +16  8  len  usize (= map width)
    """

    cap = U64(_VEC_CAP_OFF)
    ptr = U64(_VEC_PTR_OFF)
    len = U64(_VEC_LEN_OFF)

    def __len__(self) -> int:
        return self.len

    def __getitem__(self, x: int) -> Environment:
        n = self.len
        if x < 0:
            x += n
        if x < 0 or x >= n:
            raise IndexError(x)
        return _ENV_FROM_INT[self._raw.read_u8(self.ptr + x)]

    def __setitem__(self, x: int, val: Environment) -> None:
        n = self.len
        if x < 0:
            x += n
        if x < 0 or x >= n:
            raise IndexError(x)
        self._raw.write_u8(self.ptr + x, _ENV_TO_INT[val])

    def __iter__(self) -> Iterator[Environment]:
        ptr = self.ptr
        for i in range(self.len):
            yield _ENV_FROM_INT[self._raw.read_u8(ptr + i)]


class EnvGrid(RustStruct):
    """
    `Vec<Vec<Environment>>` (24 B): outer vector indexed by y.

      +0   8  cap  usize
      +8   8  ptr  *Vec<Environment>
      +16  8  len  usize (= map height)
    """

    cap = U64(_VEC_CAP_OFF)
    ptr = U64(_VEC_PTR_OFF)
    len = U64(_VEC_LEN_OFF)

    def __len__(self) -> int:
        return self.len

    def __getitem__(self, y: int) -> EnvRow:
        n = self.len
        if y < 0:
            y += n
        if y < 0 or y >= n:
            raise IndexError(y)
        return EnvRow(self._raw, self.ptr + y * _VEC_SIZE)

    def __iter__(self) -> Iterator[EnvRow]:
        ptr = self.ptr
        for i in range(self.len):
            yield EnvRow(self._raw, ptr + i * _VEC_SIZE)


class TurnDiffs(RustStruct):
    """
    `Vec<GameDiff>` (24 B): one turn's worth of diffs.

      +0   8  cap  usize
      +8   8  ptr  *GameDiff
      +16  8  len  usize
    """

    cap = U64(_VEC_CAP_OFF)
    ptr = U64(_VEC_PTR_OFF)
    len = U64(_VEC_LEN_OFF)

    def __len__(self) -> int:
        return self.len

    def __getitem__(self, i: int) -> GameDiff:
        n = self.len
        if i < 0:
            i += n
        if i < 0 or i >= n:
            raise IndexError(i)
        return GameDiff(self._raw, self.ptr + i * GameDiff.SIZE)

    def __iter__(self) -> Iterator[GameDiff]:
        ptr = self.ptr
        for i in range(self.len):
            yield GameDiff(self._raw, ptr + i * GameDiff.SIZE)


class Diffs(RustStruct):
    """
    `Vec<Vec<GameDiff>>` (24 B): one entry per turn pushed via `new_turn`.
    """

    cap = U64(_VEC_CAP_OFF)
    ptr = U64(_VEC_PTR_OFF)
    len = U64(_VEC_LEN_OFF)

    def __len__(self) -> int:
        return self.len

    def __getitem__(self, i: int) -> TurnDiffs:
        n = self.len
        if i < 0:
            i += n
        if i < 0 or i >= n:
            raise IndexError(i)
        return TurnDiffs(self._raw, self.ptr + i * _VEC_SIZE)

    def __iter__(self) -> Iterator[TurnDiffs]:
        ptr = self.ptr
        for i in range(self.len):
            yield TurnDiffs(self._raw, ptr + i * _VEC_SIZE)


class ReplayRecorder(RustStruct):
    """
    ReplayRecorder (80 B, align 8):

      +0   24   environment           Vec<Vec<Environment>> | cores
      +24  24   cores                 Vec<(Pos, Team)>      | environment
      +48  24   diffs                 Vec<Vec<GameDiff>>
      +72  1    suppress_indicators   bool

    The first two fields are both 24 B Vec triples; the disassembly of
    `append` only fingerprints `diffs` (at +48) and `suppress_indicators`
    (at +72). `cores` (+24) is not exposed; `environment` (+0) is exposed
    as `EnvGrid` (writable `Vec<Vec<u8>>` indexed [y][x]).
    """

    SIZE: Final = 80
    _ENV_OFF: Final = 0
    _DIFFS_OFF: Final = 48
    _SUPPRESS_OFF: Final = 72

    environment = Inner(_ENV_OFF, EnvGrid)
    suppress_indicators = U8(_SUPPRESS_OFF)
    diffs = Inner(_DIFFS_OFF, Diffs)

    def __init__(self, raw: RawMem, addr: int) -> None:
        super().__init__(raw, addr)

    @property
    def current_turn(self) -> TurnDiffs:
        """The `Vec<GameDiff>` for the current (last) turn. Panics if no
        turn has been started."""
        d = self.diffs
        if d.len == 0:
            msg = "no turns recorded yet"
            raise IndexError(msg)
        return d[-1]

    @property
    def last_diff(self) -> GameDiff:
        """The most recently appended `GameDiff` in the current turn."""
        return self.current_turn[-1]

    @property
    def last_place_entity(self) -> GameDiff:
        """The most recent PlaceEntity diff in the current turn (tag == None).

        Searching backward is necessary because engines >= 1.8 append
        SetActionCooldown after spawn/build, so last_diff is not PlaceEntity.
        """
        turn = self.current_turn
        for i in range(len(turn) - 1, -1, -1):
            d = turn[i]
            if d.tag is None:
                return d
        msg = "no PlaceEntity diff in current turn"
        raise LookupError(msg)

    @property
    def last_fire_turret(self) -> GameDiff:
        """The most recent FireTurret diff in the current turn (tag == 11).

        Searching backward is necessary because fire() appends SetActionCooldown
        after FireTurret via finish_firing_turret.
        """
        turn = self.current_turn
        for i in range(len(turn) - 1, -1, -1):
            d = turn[i]
            if d.tag == _TAG_FIRE_TURRET:
                return d
        msg = f"no FireTurret diff (tag={_TAG_FIRE_TURRET}) in current turn"
        raise LookupError(msg)

    @property
    def last_move_builder_bot(self) -> GameDiff:
        """The most recent MoveBuilderBot diff in the current turn (tag == 1)."""
        turn = self.current_turn
        [d.tag for d in turn]
        for i in range(len(turn) - 1, -1, -1):
            d = turn[i]
            if d.tag == _TAG_MOVE_BUILDER_BOT:
                return d
        msg = f"no MoveBuilderBot diff (tag={_TAG_MOVE_BUILDER_BOT}) in current turn"
        raise LookupError(msg)
