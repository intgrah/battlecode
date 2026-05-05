from __future__ import annotations

from cambc import ResourceType

from rust.base import i32, option
from rust.entity.variant import Variant


class Foundry(Variant):
    """
    Bucket (72 B):

      +0   4   key                 i32
      +8   8   discriminant        u64  (niche: tag 6)
      +16  4   stored_resource_id  i32                    (undefined when stored is None)
      +20  1   stored              Option<ResourceType>   (3 = None)
      +24  24  entity              EntityBase
    """

    _BASE_OFF = 24

    stored_resource_id = i32(16)
    stored = option(20, tuple(ResourceType), niche=3)

    def __repr__(self) -> str:
        s = self.stored
        return (
            f"Foundry({self._base_repr()} "
            f"stored={s.name if s else None} stored_resource_id={self.stored_resource_id})"
        )
