"""
Translation of `bots/intgrah/v54.7.9/core/spawn_tempo.py`.

Spawn tempo: a per-game scalar derived from map features visible to the
Core at `post_init` time. Higher tempo -> spawn more aggressively; lower
tempo -> spawn slower (denser walls, eccentric core, etc.).

Constants were fitted from hand-rated maps (1-5 scale, "how many builders
should this map spawn") and folded through the affine transform
`tempo = 1.0 + (rating - 3.0) * 0.15`, so the model maps features
directly to a tempo multiplier centred on 1.0.
"""
from __future__ import annotations

from typing import Final

from cambc import Environment, Position
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
BIAS: Final[float] = 1.6306
W_ECCENTRICITY: Final[float] = -0.5978
W_EDGE_DIST: Final[float] = -0.0143
W_CARDINAL_EXITS: Final[float] = -0.0114
W_INNER_WALL_DENSITY: Final[float] = -0.2698
W_OUTER_WALL_DENSITY: Final[float] = -0.2340
W_NEAREST_TI_D2: Final[float] = -0.0109
W_NEAREST_WALL_D2: Final[float] = -0.0015
CORE_VISION_R2: Final[int] = 36
INNER_R2: Final[int] = 8

def compute_spawn_tempo(width, height, ct):
    """
    Compute the spawn-tempo multiplier directly from post_init-visible map
    features. ~1.0 for an average map; ~0.7 for low-spawn maps (eccentric
    core, dense walls, far ore); ~1.3 for high-spawn maps (central, open,
    ore-rich nearby).
    """
    pos = ct.get_position(None)
    cx = pos.x
    cy = pos.y
    w = width
    h = height
    centre_dist = max(abs(cx - w // 2), abs(cy - h // 2))
    eccentricity = float(centre_dist) / float(max(max(w, h), 1))
    edge_dist = min(min(min(cx, cy), w - 1 - cx), h - 1 - cy)
    cardinal_exits: int = 0
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
        x = cx + dx
        y = cy + dy
        if x >= 0 and x < w and y >= 0 and y < h:
            env = ct.get_tile_env(Position(x=x, y=y))
            if env != Environment.WALL:
                cardinal_exits += 1
    inner_walls: int = 0
    inner_total: int = 0
    outer_walls: int = 0
    outer_total: int = 0
    nearest_ti_d2: int = 36 + 1
    nearest_wall_d2: int = 36 + 1
    for dy in range(-6, (6) + 1):
        for dx in range(-6, (6) + 1):
            d2 = dx * dx + dy * dy
            if d2 > 36:
                continue
            x = cx + dx
            y = cy + dy
            if not (x >= 0 and x < w and y >= 0 and y < h):
                continue
            env = ct.get_tile_env(Position(x=x, y=y))
            is_wall = env == Environment.WALL
            if d2 <= 8:
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
    inner_wall_density = float(inner_walls) / float(max(inner_total, 1))
    outer_wall_density = float(outer_walls) / float(max(outer_total, 1))
    return (-0.0109 * float(nearest_ti_d2) + (-0.2340 * outer_wall_density + (-0.2698 * inner_wall_density + (-0.0114 * float(cardinal_exits) + (-0.0143 * float(edge_dist) + (-0.5978 * eccentricity + 1.6306)))))) + -0.0015 * float(nearest_wall_d2)
