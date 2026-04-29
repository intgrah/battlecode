"""Spawn tempo: a per-game scalar derived from map features visible to
the Core at `post_init` time. Higher tempo → spawn more aggressively;
lower tempo → spawn slower (denser walls, eccentric core, etc.).

Constants were fitted from hand-rated maps (1-5 scale, "how many
builders should this map spawn") and folded through the affine
transform `tempo = 1.0 + (rating - 3.0) * 0.15`, so the model maps
features directly to a tempo multiplier centred on 1.0:
  rating 1 -> tempo 0.70
  rating 3 -> tempo 1.00
  rating 5 -> tempo 1.30

The features are:
- eccentricity (core chebyshev to map centre, normalised by max(w, h))
- edge_dist (chebyshev to nearest map edge)
- cardinal_exits (number of cardinal-adjacent passable tiles to the 3x3)
- inner_wall_density (walls within r²<=8 of core)
- outer_wall_density (walls in 8 < r²<=36 of core)
- nearest_ti_d2 (squared distance to closest visible Ti ore; 37 if none)
- nearest_wall_d2 (squared distance to closest visible wall; 37 if none)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Environment, Position

if TYPE_CHECKING:
    from cambc import Controller

    from core import Core


# Folded constants: each = 0.15 * raw_linear_coef, plus the bias term
# carries the +1.0 - 3.0*0.15 offset.
_BIAS: Final = 1.6306
_W_ECCENTRICITY: Final = -0.5978
_W_EDGE_DIST: Final = -0.0143
_W_CARDINAL_EXITS: Final = -0.0114
_W_INNER_WALL_DENSITY: Final = -0.2698
_W_OUTER_WALL_DENSITY: Final = -0.2340
_W_NEAREST_TI_D2: Final = -0.0109
_W_NEAREST_WALL_D2: Final = -0.0015

_CORE_VISION_R2: Final = 36
_INNER_R2: Final = 8


def compute_spawn_tempo(self: Core, ct: Controller) -> float:
    """Compute the spawn-tempo multiplier directly from post_init-visible
    map features. ~1.0 for an average map; ~0.7 for low-spawn maps
    (eccentric core, dense walls, far ore); ~1.3 for high-spawn maps
    (central, open, ore-rich nearby).
    """
    pos = ct.get_position()
    cx, cy = pos.x, pos.y
    w, h = self.w, self.h

    centre_dist = max(abs(cx - w // 2), abs(cy - h // 2))
    eccentricity = centre_dist / max(w, h, 1)
    edge_dist = min(cx, cy, w - 1 - cx, h - 1 - cy)

    cardinal_exits = 0
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        x, y = cx + dx, cy + dy
        if 0 <= x < w and 0 <= y < h:
            env = ct.get_tile_env(Position(x, y))
            if env != Environment.WALL:
                cardinal_exits += 1

    inner_walls = 0
    inner_total = 0
    outer_walls = 0
    outer_total = 0
    nearest_ti_d2 = _CORE_VISION_R2 + 1
    nearest_wall_d2 = _CORE_VISION_R2 + 1

    for dy in range(-6, 7):
        for dx in range(-6, 7):
            d2 = dx * dx + dy * dy
            if d2 > _CORE_VISION_R2:
                continue
            x, y = cx + dx, cy + dy
            if not (0 <= x < w and 0 <= y < h):
                continue
            env = ct.get_tile_env(Position(x, y))
            is_wall = env == Environment.WALL
            if d2 <= _INNER_R2:
                inner_total += 1
                if is_wall:
                    inner_walls += 1
            else:
                outer_total += 1
                if is_wall:
                    outer_walls += 1
            if is_wall and d2 < nearest_wall_d2:
                nearest_wall_d2 = d2
            if env == Environment.ORE_TITANIUM and d2 < nearest_ti_d2:
                nearest_ti_d2 = d2

    inner_wall_density = inner_walls / max(inner_total, 1)
    outer_wall_density = outer_walls / max(outer_total, 1)

    return (
        _BIAS
        + _W_ECCENTRICITY * eccentricity
        + _W_EDGE_DIST * edge_dist
        + _W_CARDINAL_EXITS * cardinal_exits
        + _W_INNER_WALL_DENSITY * inner_wall_density
        + _W_OUTER_WALL_DENSITY * outer_wall_density
        + _W_NEAREST_TI_D2 * nearest_ti_d2
        + _W_NEAREST_WALL_D2 * nearest_wall_d2
    )
