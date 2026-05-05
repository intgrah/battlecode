from __future__ import annotations

from typing import Final

from cambc import ResourceType

from rust.base import i32, option, position
from rust.entity.variant import Variant


class Bridge(Variant):
    """
    Bucket (72 B):

      +0   4   key                 i32
      +8   8   discriminant        u64  (niche: tag 4)
      +16  8   target              Position
      +24  4   stored_resource_id  i32                    (undefined when stored is None)
      +28  1   stored              Option<ResourceType>   (3 = None)
      +32  24  entity              EntityBase
    """

    _BASE_OFF = 32
    _TARGET_OFF: Final = 16

    target = position(_TARGET_OFF)
    stored_resource_id = i32(24)
    stored = option(28, tuple(ResourceType), niche=3)

    def __repr__(self) -> str:
        s = self.stored
        return (
            f"Bridge({self._base_repr()} "
            f"target={self.target} "
            f"stored={s.name if s else None} stored_resource_id={self.stored_resource_id})"
        )
