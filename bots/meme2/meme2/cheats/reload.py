"""Reload a turret's ammo from thin air, with the resource type of our choice.

Mechanism: every turret stores `ammo_amount: i32` and
`ammo_type: Option<ResourceType>` directly in its entity bucket. The engine
reads these at fire time and decrements `ammo_amount` after a shot, but
never validates against the stored resource — it just trusts the bucket.
Writing the bucket fields directly bypasses the conveyor/foundry feed path
and the "one stack only" cap.

No replay diff is emitted by an ammo write, so there is nothing to patch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rust import EntityBreach, EntityGunner, EntitySentinel, Game

if TYPE_CHECKING:
    from cambc import Controller, ResourceType


def reload(g: Game, ct: Controller, ammo_type: ResourceType, amount: int = 10) -> None:
    """Set the calling turret's ammo to `(ammo_type, amount)` directly.

    Caller must be a Gunner/Sentinel/Breach. `amount` is not capped — feeds
    above one stack (10) work and persist.
    """
    me = g.entities[ct.get_id()].as_variant
    assert isinstance(me, (EntityGunner, EntitySentinel, EntityBreach))
    me.ammo_type = ammo_type
    me.ammo_amount = amount
