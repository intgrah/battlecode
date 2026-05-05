from __future__ import annotations

from typing import Final

from rust.base import u32
from rust.entity import Variant


class Marker(Variant):
    """
    Bucket (72 B):

      +0   4   key           i32
      +8   8   discriminant  u64  (niche: tag 9)
      +16  4   value         u32
      +20  24  entity        EntityBase
    """

    _BASE_OFF: Final = 20

    value = u32(16)
