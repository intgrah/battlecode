from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import U64, RustStruct
from rust.game_diff.fire_turret import GameDiffFireTurret
from rust.game_diff.place_entity import GameDiffPlaceEntity
from rust.game_diff.remove_entity import GameDiffRemoveEntity
from rust.game_diff.variant import GameDiffVariant  # noqa: TC001

if TYPE_CHECKING:
    from rust.raw_mem import RawMem

# GameDiff is a niche-encoded tagged enum (72 B, align 8).
#
# Discriminant occupies GameDiff[0..8] as a u64. PlaceEntity is the niche
# variant — its bytes are the inner Entity, whose own niche guarantees the
# high bit of word0 is meaningful (clear → variant 0). Non-niche variants
# encode their tag as `(1 << 63) | (0xe + idx)`, where `idx` is the source
# declaration order (1 = MoveBuilderBot, …, 11 = FireTurret, 12 = the
# gunner-fire variant added in the rotate balance change).
_NICHE_BASE: Final = 0x800000000000000E
_TAG_REMOVE_ENTITY: Final = 2
_TAG_FIRE_TURRET: Final = 12


class GameDiff(RustStruct):
    """
    GameDiff (72 B): niche-encoded tagged enum stored in
    `Vec<Vec<GameDiff>>` inside `ReplayRecorder`.

      +0   8   discriminant   u64
      +8   N   payload        variant-dependent
    """

    SIZE: Final = 72
    _DISC_OFF: Final = 0

    _disc = U64(_DISC_OFF)

    def __init__(self, raw: RawMem, addr: int) -> None:
        super().__init__(raw, addr)

    @property
    def tag(self) -> int | None:
        """Source-order variant index, or `None` for the niche variant
        (`PlaceEntity`).

        PlaceEntity reuses Entity's own niche space, so its discriminant
        bytes can be either high-bit-clear (EntityCore) or `(1<<63) | t`
        for entity tag `t in {0..9, 11..14}`. Non-niche GameDiff variants
        start at `_NICHE_BASE + 1` (= MoveBuilderBot, idx 1). Anything at
        or below `_NICHE_BASE` is the niche variant."""
        w = self._disc
        if w <= _NICHE_BASE:
            return None
        return w - _NICHE_BASE

    @property
    def as_variant(self) -> GameDiffVariant:
        """Construct the typed variant subclass for this diff. Only
        `FireTurret` is implemented; other tags raise."""
        match self.tag:
            case None:
                return GameDiffPlaceEntity(self._raw, self._addr)
            case t if t == _TAG_REMOVE_ENTITY:
                return GameDiffRemoveEntity(self._raw, self._addr)
            case t if t == _TAG_FIRE_TURRET:  # 12 in installed binary (extra variant before FireTurret)
                return GameDiffFireTurret(self._raw, self._addr)
            case other:
                msg = f"GameDiff tag {other!r} not yet wrapped"
                raise NotImplementedError(msg)

    def __repr__(self) -> str:
        try:
            return repr(self.as_variant)
        except NotImplementedError:
            return f"GameDiff(tag={self.tag})"
