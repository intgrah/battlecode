from __future__ import annotations

from rust.base import Pos
from rust.game_diff.variant import GameDiffVariant


class GameDiffFireTurret(GameDiffVariant):
    """
    GameDiff::FireTurret (72 B):

      +0   8   discriminant     u64  (niche tag = 0x800000000000001a, idx=12 in installed binary)
      +8   8   from             Pos
      +16  8   to               Pos
      +24  48  padding
    """

    _FROM_OFF = 8
    _TO_OFF = 16

    from_ = Pos(_FROM_OFF)
    to = Pos(_TO_OFF)

    def __repr__(self) -> str:
        return f"GameDiffFireTurret(from={self.from_} to={self.to})"
