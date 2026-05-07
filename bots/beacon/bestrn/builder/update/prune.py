from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder


def prune_stale(builder, ct):
    builder.nearby_buildings = []
    builder.healable_buildings = list(
        (p for p in builder.healable_buildings if not ct.is_in_vision(p))
    )
    builder.adjacent_to_enemy_launcher = set(
        (p for p in builder.adjacent_to_enemy_launcher if not ct.is_in_vision(p))
    )
    builder.enemy_turret_ray_tiles = set(
        (p for p in builder.enemy_turret_ray_tiles if not ct.is_in_vision(p))
    )
    builder.friendly_turret_ray_tiles = set(
        (p for p in builder.friendly_turret_ray_tiles if not ct.is_in_vision(p))
    )
