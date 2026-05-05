from __future__ import annotations

from rust.base import i32
from rust.entity.variant import Variant


class Launcher(Variant):
    """
    Bucket (72 B):

      +0   4   key              i32
      +8   8   discriminant     u64  (niche: tag 14)
      +20  4   action_cooldown  i32
      +28  24  entity           EntityBase

    No ammo, no direction (launchers throw builder bots; per-game-rules
    they have no ammo or facing). The TurretBase ammo slots exist in
    the bucket but are never used.
    """

    _BASE_OFF = 28

    action_cooldown = i32(20)

    def __repr__(self) -> str:
        return f"Launcher({self._base_repr()} action_cd={self.action_cooldown})"
