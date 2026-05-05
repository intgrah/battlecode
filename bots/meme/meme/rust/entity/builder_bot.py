from __future__ import annotations

from typing import Final

from rust.base import i32
from rust.entity import Variant


class BuilderBot(Variant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   8   discriminant     u64  (niche: tag 0)
      +16  4   action_cooldown  i32
      +20  4   move_cooldown    i32
      +24  24  entity           EntityBase
    """

    _BASE_OFF: Final = 24

    action_cooldown = i32(16)
    move_cooldown = i32(20)
