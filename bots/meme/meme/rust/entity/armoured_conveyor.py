from __future__ import annotations

from cambc import Direction, ResourceType

from rust.base import enum_u8, i32, option
from rust.entity.variant import Variant


class ArmouredConveyor(Variant):
    """
    Bucket (72 B):

      +0   4   key                 i32
      +8   8   discriminant        u64  (niche: tag 3)
      +16  4   stored_resource_id  i32                    (undefined when stored is None)
      +20  1   stored              Option<ResourceType>   (3 = None)
      +24  24  entity              EntityBase
      +48  1   direction           Direction
    """

    _BASE_OFF = 24

    stored_resource_id = i32(16)
    stored = option(20, tuple(ResourceType), niche=3)
    direction = enum_u8(48, tuple(Direction))

    def __repr__(self) -> str:
        s = self.stored
        return (
            f"ArmouredConveyor({self._base_repr()} "
            f"direction={self.direction.name} "
            f"stored={s.name if s else None} stored_resource_id={self.stored_resource_id})"
        )
