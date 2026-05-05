from __future__ import annotations

from typing import Final

from cambc import ResourceType

from rust.base import enum_u8, i32, position
from rust.entity.variant import Variant


class Harvester(Variant):
    """
    Bucket (72 B):

      +0   4   key            i32
      +8   8   discriminant   u64  (niche: tag 5)
      +16  4   cooldown       i32
      +20  24  entity         EntityBase
      +44  1   resource_type  ResourceType
      +48  8   target_pos     Position  (the ore tile being mined)
    """

    _BASE_OFF = 20
    _TARGET_POS_OFF: Final = 48

    cooldown = i32(16)
    resource_type = enum_u8(44, tuple(ResourceType))
    target_pos = position(_TARGET_POS_OFF)

    def __repr__(self) -> str:
        return (
            f"Harvester({self._base_repr()} "
            f"cooldown={self.cooldown} resource_type={self.resource_type.name} "
            f"target_pos={self.target_pos})"
        )
