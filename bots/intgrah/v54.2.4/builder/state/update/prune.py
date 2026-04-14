from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller

    from builder.state import State


def prune_stale(state: State, ct: Controller) -> None:
    w = state.w
    nearby_positions = ct.get_nearby_tiles()
    state.nearby_positions = nearby_positions
    state.nearby_buildings = []

    state.healable_buildings = [
        p for p in state.healable_buildings if not ct.is_in_vision(p)
    ]
    state.adjacent_to_enemy_launcher = {
        p for p in state.adjacent_to_enemy_launcher if not ct.is_in_vision(p)
    }
    state.enemy_turret_ray_tiles = {
        p for p in state.enemy_turret_ray_tiles if not ct.is_in_vision(p)
    }
    state.friendly_turret_ray_tiles = {
        p for p in state.friendly_turret_ray_tiles if not ct.is_in_vision(p)
    }

    for pos in nearby_positions:
        if 0 <= pos.x < state.w and 0 <= pos.y < state.h:
            i = pos.y * w + pos.x
            state.conveyors_to_here[i] = [
                p for p in state.conveyors_to_here[i] if not ct.is_in_vision(p)
            ]
            state.splitters_to_here[i] = [
                p for p in state.splitters_to_here[i] if not ct.is_in_vision(p)
            ]
