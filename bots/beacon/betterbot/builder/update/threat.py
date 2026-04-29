"""Soft cost-grid penalty for tiles threatened by enemy turrets and
launchers. Bumps `cost_grid[i]` by `THREAT_PENALTY` so dp_step's
weighted tiebreak detours around them when an alternate tile of equal
plan-progress exists. Reverted-and-reapplied each turn so the bump
only persists while the threat set still contains the tile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH

from builder.update.vision import _update_cost

if TYPE_CHECKING:
    from builder import Builder

THREAT_PENALTY = 50
"""Additive penalty applied to threatened tiles. Sized so dp_step
prefers a detour of up to ~16 extra ROAD_COST hops (50 / 3) over
walking through a turret ray."""


def apply_threat_overlay(self: Builder) -> None:
    bumped = self._threat_bumped
    cost_grid = self.cost_grid
    env = self.env
    buildings = self.buildings
    for i in bumped:
        _update_cost(self, i, env[i], buildings[i])
    bumped.clear()

    for tile in self.enemy_turret_ray_tiles:
        i = tile.y * MAX_WIDTH + tile.x
        if cost_grid[i] is not INF and i not in bumped:
            cost_grid[i] += THREAT_PENALTY
            bumped.add(i)
    for tile in self.adjacent_to_enemy_launcher:
        i = tile.y * MAX_WIDTH + tile.x
        if cost_grid[i] is not INF and i not in bumped:
            cost_grid[i] += THREAT_PENALTY
            bumped.add(i)
