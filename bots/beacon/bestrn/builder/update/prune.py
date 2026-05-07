from __future__ import annotations


def prune_stale(builder, ct) -> None:
    builder.nearby_buildings = []
    builder.healable_buildings = [
        p for p in builder.healable_buildings if not ct.is_in_vision(p)
    ]
    builder.adjacent_to_enemy_launcher = {
        p for p in builder.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
    }
    builder.enemy_turret_ray_tiles = {
        p for p in builder.enemy_turret_ray_tiles if not ct.is_in_vision(p)
    }
    builder.friendly_turret_ray_tiles = {
        p for p in builder.friendly_turret_ray_tiles if not ct.is_in_vision(p)
    }
