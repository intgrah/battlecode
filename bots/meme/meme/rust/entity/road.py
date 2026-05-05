from __future__ import annotations

from rust.entity.variant import EntityVariant


class EntityRoad(EntityVariant):
    """
    Bucket (72 B):

      +0   4   key           i32
      +8   8   discriminant  u64  (niche: tag 7)
      +16  24  entity        EntityBase
    """

    _BASE_OFF = 16
