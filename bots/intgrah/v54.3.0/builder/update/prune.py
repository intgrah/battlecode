from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def prune_stale(self: Builder, ct: Controller) -> None:
    w = self.w
    nearby_positions = ct.get_nearby_tiles()
    self.nearby_positions = nearby_positions
    self.nearby_buildings = []

    self.healable_buildings = [
        p for p in self.healable_buildings if not ct.is_in_vision(p)
    ]
    self.adjacent_to_enemy_launcher = {
        p for p in self.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
    }
    self.enemy_turret_ray_tiles = {
        p for p in self.enemy_turret_ray_tiles if not ct.is_in_vision(p)
    }
    self.friendly_turret_ray_tiles = {
        p for p in self.friendly_turret_ray_tiles if not ct.is_in_vision(p)
    }

    for pos in nearby_positions:
        i = pos.y * w + pos.x
        self.conveyors_to_here[i] = [
            p for p in self.conveyors_to_here[i] if not ct.is_in_vision(p)
        ]
        self.splitters_to_here[i] = [
            p for p in self.splitters_to_here[i] if not ct.is_in_vision(p)
        ]
