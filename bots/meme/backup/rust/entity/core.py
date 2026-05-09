from __future__ import annotations

from typing import Final

from rust.base import I32, Inner
from rust.entity.variant import EntityVariant
from rust.vec import Vec


class EntityCore(EntityVariant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   24  received         Vec<ResourceType>  (cap @+8 doubles as discriminant)
      +32  4   action_cooldown  i32
      +36  4   _move_cooldown   i32  (unused — cores don't move)
      +40  24  entity           EntityBase
      +64  8   ???              ???  (variant-shared trailing slot)
    """

    _BASE_OFF = 40
    _RECEIVED_OFF: Final = 8

    action_cooldown = I32(32)
    received = Inner(_RECEIVED_OFF, Vec)

    def __repr__(self) -> str:
        v = self.received
        return (
            f"EntityCore({self._base_repr()} "
            f"action_cd={self.action_cooldown} "
            f"received(cap={v.cap}, len={v.len}))"
        )
