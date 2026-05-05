from __future__ import annotations

from rust.entity.variant import Variant


class Barrier(Variant):
    """
    Bucket (72 B):

      +0   4   key           i32
      +8   8   discriminant  u64  (niche: tag 8)
      +16  24  entity        EntityBase
    """

    _BASE_OFF = 16
