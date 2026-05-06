from __future__ import annotations

from rust.base import I32
from rust.game_diff.variant import GameDiffVariant


class GameDiffRemoveEntity(GameDiffVariant):
    """
    GameDiff::RemoveEntity (72 B):

      +0   8   discriminant   u64  (= _NICHE_BASE + 2)
      +8   4   id             i32
      +12  60  padding
    """

    id = I32(8)

    def __repr__(self) -> str:
        return f"GameDiffRemoveEntity(id={self.id})"
