from __future__ import annotations

from typing import Final

from rust.entity import Variant


class Road(Variant):
    """
    Bucket (72 B):

      +0   4   key           i32
      +8   8   discriminant  u64  (niche: tag 7)
      +16  24  entity        EntityBase
    """

    _BASE_OFF: Final = 16
