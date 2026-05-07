"""
Soft cost-grid penalty for tiles threatened by enemy turrets and
launchers. Bumps `cost_grid[i]` by `THREAT_PENALTY` so `dp_step`'s
weighted tiebreak detours around them when an alternate tile of equal
plan-progress exists. Reverted-and-reapplied each turn so the bump
only persists while the threat set still contains the tile.
"""

from __future__ import annotations

from typing import Final

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder import Builder
from builder.update.vision import _update_cost
from util.constants import INF, MAX_WIDTH

THREAT_PENALTY: Final[int] = 50
"""
Additive penalty applied to threatened tiles. Sized so `dp_step`
prefers a detour of up to ~16 extra `ROAD_COST` hops (50 / 3) over
walking through a turret ray.
"""


def apply_threat_overlay(builder):
    bumped_indices: list[int] = list(builder._threat_bumped)
    for i in bumped_indices:
        env = builder.env[i]
        kind = builder.building_kind[i]
        team = builder.building_team[i]
        _update_cost(builder, i, env, kind, team)
    builder._threat_bumped.clear()
    enemy_tiles: list[object] = list(builder.enemy_turret_ray_tiles)
    for tile in enemy_tiles:
        i = int(tile.y) * 50 + int(tile.x)
        if builder.cost_grid[i] != 1000000 and not (i in builder._threat_bumped):
            builder.cost_grid[i] += 50
            builder._threat_bumped.add(i)
    launcher_tiles: list[object] = list(builder.adjacent_to_enemy_launcher)
    for tile in launcher_tiles:
        i = int(tile.y) * 50 + int(tile.x)
        if builder.cost_grid[i] != 1000000 and not (i in builder._threat_bumped):
            builder.cost_grid[i] += 50
            builder._threat_bumped.add(i)
