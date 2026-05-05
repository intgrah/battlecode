from __future__ import annotations

from rust.base import i32
from rust.entity.variant import Variant


class BuilderBot(Variant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   8   discriminant     u64  (niche: tag 0)
      +16  4   action_cooldown  i32
      +20  4   move_cooldown    i32
      +24  24  entity           EntityBase
    """

    _BASE_OFF = 24

    action_cooldown = i32(16)
    move_cooldown = i32(20)

    def __repr__(self) -> str:
        return (
            f"BuilderBot({self._base_repr()} "
            f"action_cd={self.action_cooldown} move_cd={self.move_cooldown})"
        )
