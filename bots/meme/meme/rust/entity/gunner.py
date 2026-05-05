from __future__ import annotations

from typing import Final

from cambc import Direction, ResourceType

from rust.base import enum_u8, i32, option
from rust.entity import Variant


class Gunner(Variant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   8   discriminant     u64  (niche: tag 11)
      +16  4   ammo_amount      i32
      +20  4   action_cooldown  i32
      +28  24  entity           EntityBase
      +56  1   ammo_type        Option<ResourceType>  (3 = None)
      +60  1   direction        Direction
    """

    _BASE_OFF: Final = 28

    ammo_amount = i32(16)
    action_cooldown = i32(20)
    ammo_type = option(56, tuple(ResourceType), niche=3)
    direction = enum_u8(60, tuple(Direction))
