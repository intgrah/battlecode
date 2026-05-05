from __future__ import annotations

from typing import Final

from rust.base import i32
from rust.entity import Variant
from rust.vec import Vec


class Core(Variant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   24  received         Vec<ResourceType>  (cap @+8 doubles as discriminant)
      +32  4   action_cooldown  i32
      +36  4   _move_cooldown   i32  (unused — cores don't move)
      +40  24  entity           EntityBase
      +64  8   ???              ???  (variant-shared trailing slot)
    """

    _BASE_OFF: Final = 40
    _RECEIVED_OFF: Final = 8

    action_cooldown = i32(32)

    @property
    def received(self) -> Vec:
        return Vec(self._raw, self._addr + Core._RECEIVED_OFF)
