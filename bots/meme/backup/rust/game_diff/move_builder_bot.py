from __future__ import annotations

from rust.base import I32, Pos
from rust.game_diff.variant import GameDiffVariant


class GameDiffMoveBuilderBot(GameDiffVariant):
    """
    GameDiff::MoveBuilderBot (72 B):

      +0   8   discriminant   u64  (= _NICHE_BASE + 1)
      +8   8   to             Pos
      +16  4   id             i32
      +20  52  padding
    """

    to = Pos(8)
    id = I32(16)

    def __repr__(self) -> str:
        return f"GameDiffMoveBuilderBot(id={self.id} to={self.to})"
