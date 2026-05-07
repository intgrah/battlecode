"""Fire a turret at any in-bounds tile, ignoring its range and facing geometry.

Mechanism: every turret's `*_target_valid` check reads `turret.position` (and
`turret.direction`) from the entity bucket and computes Chebyshev/cone/ray
geometry from there. Spoofing the bucket's `position` field to a tile
adjacent to `target` along the turret's facing direction makes the check
pass; the actual `damage_tile` call still uses the `target` we passed in,
so damage lands wherever we want.

The engine emits a `GameDiff::FireTurret { from, to }` synchronously inside
`fire_*`, reading `from` from the spoofed `turret.position`. We restore the
real position immediately after `ct.fire` returns and patch the just-written
diff so the replay shows the truthful `from`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rust import (
    EntityBreach,
    EntityGunner,
    EntitySentinel,
    Game,
    GameDiffFireTurret,
)

if TYPE_CHECKING:
    from cambc import Controller, Position


def fire_anywhere(g: Game, ct: Controller, target: Position) -> None:
    """Fire the calling turret at `target`, bypassing the range check.

    Caller must be a Gunner/Sentinel/Breach. `target` must be in bounds.
    Costs one fire's worth of ammo and applies the turret's normal cooldown.
    """
    me = g.entities[ct.get_id()].as_variant
    assert isinstance(me, (EntityGunner, EntitySentinel, EntityBreach))

    pos = me.base.position
    me.base.position = target.add(me.direction.opposite())  # Spoof
    ct.fire(target)
    me.base.position = pos

    last = g.replay_recorder.last_diff.as_variant
    if isinstance(last, GameDiffFireTurret):
        last.from_ = pos
