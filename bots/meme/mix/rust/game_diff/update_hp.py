from __future__ import annotations

from rust.base import I32
from rust.game_diff.variant import GameDiffVariant


class GameDiffUpdateHp(GameDiffVariant):
    """
    GameDiff::UpdateHp (72 B):

      +0   8   discriminant   u64  (= _NICHE_BASE + 4)
      +8   4   id             i32
      +12  4   delta          i32
      +16  56  padding
    """

    id = I32(8)
    delta = I32(12)

    def __repr__(self) -> str:
        return f"GameDiffUpdateHp(id={self.id} delta={self.delta})"
