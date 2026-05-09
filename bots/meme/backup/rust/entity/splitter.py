from __future__ import annotations

from cambc import Direction, ResourceType

from rust.base import I32, EnumU8, OptionU8
from rust.entity.variant import EntityVariant


class EntitySplitter(EntityVariant):
    """
    Bucket (72 B):

      +0   4   key                 i32
      +8   8   discriminant        u64  (niche: tag 2)
      +16  4   stored_resource_id  i32                    (undefined when stored is None)
      +20  1   stored              Option<ResourceType>   (3 = None)
      +24  24  entity              EntityBase
      +48  1   direction           Direction
    """

    _BASE_OFF = 24

    stored_resource_id = I32(16)
    stored = OptionU8(20, tuple(ResourceType), niche=3)
    direction = EnumU8(48, tuple(Direction))

    def __repr__(self) -> str:
        s = self.stored
        return (
            f"EntitySplitter({self._base_repr()} "
            f"direction={self.direction.name} "
            f"stored={s.name if s else None} stored_resource_id={self.stored_resource_id})"
        )
