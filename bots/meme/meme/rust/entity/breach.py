from __future__ import annotations

from cambc import Direction, ResourceType

from rust.base import enum_u8, i32, option
from rust.entity.variant import Variant


class Breach(Variant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   8   discriminant     u64  (niche: tag 13)
      +16  4   ammo_amount      i32
      +20  4   action_cooldown  i32
      +28  24  entity           EntityBase
      +56  1   ammo_type        Option<ResourceType>  (3 = None)
      +60  1   direction        Direction
    """

    _BASE_OFF = 28

    ammo_amount = i32(16)
    action_cooldown = i32(20)
    ammo_type = option(56, tuple(ResourceType), niche=3)
    direction = enum_u8(60, tuple(Direction))

    def __repr__(self) -> str:
        a = self.ammo_type
        return (
            f"Breach({self._base_repr()} "
            f"action_cd={self.action_cooldown} direction={self.direction.name} "
            f"ammo={self.ammo_amount}x{a.name if a else None})"
        )
