"""Per-turn state dump. Adds vis nodes to the debug tree under nested
`Scope` categories (terrain, routability, distances, econ, offense,
identity, resources, misc). Every value is wrapped in a `Dump*` typed
payload so the renderer knows exactly how to display it.
"""

from __future__ import annotations

from math import sqrt
from typing import TYPE_CHECKING

from cambc import Position
from util.constants import INF, MAX_WIDTH
from util.debug import Scope, vis
from util.visualiser import (
    TRANSPARENT,
    Colour,
    DumpBoolGrid,
    DumpDot,
    DumpF32Grid,
    DumpI16Grid,
    DumpPath,
    DumpScalar,
    DumpTile,
    DumpTiles,
    Palette,
    PaletteStop,
)

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder

__all__ = ["dump"]

P_FOG = Palette(
    stops=[
        PaletteStop(t=False, colour=TRANSPARENT),
        PaletteStop(t=True, colour=Colour(0, 0, 0, 180)),
    ],
)
P_COST = Palette(
    stops=[
        PaletteStop(t=0, colour=Colour(50, 200, 50, 140)),
        PaletteStop(t=100, colour=Colour(200, 50, 50, 140)),
    ],
    special={-1: TRANSPARENT},
)
P_DIST = Palette(
    stops=[
        PaletteStop(t=0, colour=Colour(50, 240, 50, 140)),
        PaletteStop(t=36, colour=Colour(240, 50, 50, 140)),
    ],
    special={INF: TRANSPARENT, -1: TRANSPARENT},
)
P_BOOL = Palette(
    stops=[
        PaletteStop(t=False, colour=TRANSPARENT),
        PaletteStop(t=True, colour=Colour(120, 180, 240, 140)),
    ],
)
P_PATROL = Palette(
    stops=[
        PaletteStop(t=0.0, colour=Colour(80, 140, 220, 100)),
        PaletteStop(t=200.0, colour=Colour(240, 80, 80, 200)),
    ],
    special={-1.0: TRANSPARENT},
)


def _crop(arr: list[int], w: int, h: int) -> list[int]:
    """Crop a flat MAX_WIDTH x MAX_WIDTH array to actual map dimensions,
    replacing INF / >=1e6 sentinels with -1 so the palette's `special`
    table can render them as transparent.
    """
    return [
        c if c < 1e6 else -1
        for y in range(h)
        for c in arr[y * MAX_WIDTH : y * MAX_WIDTH + w]
    ]


def _crop_bool(arr: list[bool] | bytearray, w: int, h: int) -> list[bool]:
    return [bool(arr[y * MAX_WIDTH + x]) for y in range(h) for x in range(w)]


def _econ_disc_tiles(self: Builder) -> set[Position]:
    """Tiles inside our econ disc — eligible for ECON/DEFENSE ore claims.
    Cached per (my_core, econ_radius_sq) since the geometry is static.
    `dump()` is the only caller and is gated on DEBUG_DUMP."""
    cached = getattr(self, "_econ_disc_cache", None)
    key = (self.my_core, self.econ_radius_sq)
    if cached is not None and cached[0] == key:
        return cached[1]
    tiles: set[Position] = set()
    for y in range(self.h):
        for x in range(self.w):
            p = Position(x, y)
            if p.distance_squared(self.my_core) <= self.econ_radius_sq:
                tiles.add(p)
    self._econ_disc_cache = (key, tiles)
    return tiles


def _reach_roots(self: Builder, w: int, h: int) -> list[int]:
    parent = self.reach_parent
    return [parent[y * MAX_WIDTH + x] for y in range(h) for x in range(w)]


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    match i % 6:
        case 0:
            r, g, b = v, t, p
        case 1:
            r, g, b = q, v, p
        case 2:
            r, g, b = p, v, t
        case 3:
            r, g, b = p, q, v
        case 4:
            r, g, b = t, p, v
        case 5:
            r, g, b = v, p, q
        case _:
            raise AssertionError
    return int(r * 255), int(g * 255), int(b * 255)


_GOLDEN = (sqrt(5) - 1) / 2


def _reach_palette(self: Builder, w: int, h: int) -> Palette[int]:
    parent = self.reach_parent
    keys: set[int] = set()
    for y in range(h):
        base = y * MAX_WIDTH
        for x in range(w):
            v = parent[base + x]
            if v != -1:
                keys.add(v)
    special: dict[int, Colour] = {-1: TRANSPARENT}
    for k, key in enumerate(sorted(keys)):
        hue = (k * _GOLDEN) % 1.0
        r, g, b = _hsv_to_rgb(hue, 0.65, 0.95)
        special[key] = Colour(r, g, b, 160)
    return Palette(
        stops=[
            PaletteStop(t=0, colour=TRANSPARENT),
            PaletteStop(t=1, colour=TRANSPARENT),
        ],
        special=special,
    )


def dump(self: Builder, _ct: Controller) -> None:
    w, h = self.w, self.h
    env = self.env
    with Scope("dump"):
        with Scope("identity"):
            vis("id", DumpScalar(self.my_id))
            vis("pos", DumpTile(self.my_pos))
            vis("round", DumpScalar(self.round))
            vis("role", DumpScalar(str(self.role)))
            vis("role_age", DumpScalar(self.role_age))
            vis(
                "symmetry",
                DumpScalar(None if self.symmetry is None else self.symmetry.name),
            )
            vis(
                "symmetry_candidates",
                DumpScalar(", ".join(sorted(s.name for s in self.symmetry_candidates))),
            )
            vis("en_core_seen", DumpScalar(self.en_core_seen))
            vis(
                "bugnav_path",
                DumpPath(
                    self.bugnav.committed_positions(),
                    Colour(0, 200, 0, 180),
                ),
            )
            vis(
                "bugnav_goal",
                DumpDot(self.bugnav.active_goal, Colour(255, 50, 50, 220)),
            )
            vis("bugnav_gen_done", DumpScalar(self.bugnav.gen_done))
            vis("bugnav_unreachable", DumpScalar(self.bugnav.unreachable))
            vis(
                "bugnav_mline",
                DumpPath(self.bugnav.mline(), Colour(255, 200, 0, 180)),
            )
        with Scope("terrain"):
            vis(
                "unseen",
                DumpBoolGrid(
                    data=[
                        e is None
                        for y in range(h)
                        for e in env[y * MAX_WIDTH : y * MAX_WIDTH + w]
                    ],
                    palette=P_FOG,
                ),
            )
            vis(
                "cost",
                DumpI16Grid(data=_crop(self.cost_grid, w, h), palette=P_COST),
            )
            vis(
                "buildable",
                DumpBoolGrid(data=_crop_bool(self.buildable, w, h), palette=P_BOOL),
            )
        with Scope("routability"):
            vis(
                "ti_routable",
                DumpBoolGrid(data=_crop_bool(self.ti_routable, w, h), palette=P_BOOL),
            )
            vis(
                "ax_routable",
                DumpBoolGrid(data=_crop_bool(self.ax_routable, w, h), palette=P_BOOL),
            )
            vis(
                "ti_leakage",
                DumpBoolGrid(data=_crop_bool(self.ti_leakage, w, h), palette=P_BOOL),
            )
            vis(
                "ax_leakage",
                DumpBoolGrid(data=_crop_bool(self.ax_leakage, w, h), palette=P_BOOL),
            )
        with Scope("distances"):
            vis(
                "reach_root",
                DumpI16Grid(
                    data=_reach_roots(self, w, h),
                    palette=_reach_palette(self, w, h),
                ),
            )
            vis(
                "ti_conv_dist",
                DumpI16Grid(data=_crop(self.conv_search._dist, w, h), palette=P_DIST),
            )
            vis(
                "ax_conv_dist",
                DumpI16Grid(
                    data=_crop(self.ax_conv_search._dist, w, h),
                    palette=P_DIST,
                ),
            )
        with Scope("econ"):
            with Scope("targets"):
                vis("ti_ore_target", DumpTile(self.ore_target))
                vis("ax_ore_target", DumpTile(self.ax_ore_target))
                vis("offensive_ore_target", DumpTile(self.offensive_ore_target))
                vis("foundry_target", DumpTile(self.foundry_target))
                vis("ti_sink", DumpTile(self.ti_sink))
                vis("ax_sink", DumpTile(self.ax_sink))
                vis("dangling_output", DumpTile(self.dangling_output))
            with Scope("sets"):
                vis("dangling_set", DumpTiles(self.dangling_set))
                vis("unreachable_dangling", DumpTiles(self.unreachable_dangling))
                vis("reaches_core", DumpTiles(self.reaches_core))
                vis("reaches_foundry", DumpTiles(self.reaches_foundry))
                vis("ti_upstream", DumpTiles(self.ti_upstream))
                vis("ax_upstream", DumpTiles(self.ax_upstream))
                vis("upstream_of_dangling", DumpTiles(self.upstream_of_dangling))
                vis("upstream_of_congestion", DumpTiles(self.upstream_of_congestion))
                vis("junctions", DumpTiles(self.junctions))
                vis("is_multi_input", DumpTiles(self.is_multi_input))
                vis("congested_junctions", DumpTiles(self.congested_junctions))
                vis("my_foundries", DumpTiles(self.my_foundries))
            with Scope("harvesters"):
                vis("ti_harvester_adjacent", DumpTiles(self.ti_harvester_adjacent))
                vis("ax_harvester_adjacent", DumpTiles(self.ax_harvester_adjacent))
                vis("harvester_adjacent", DumpTiles(self.adjacent_to_harvester))
                vis(
                    "unconnected_harvester",
                    DumpTiles(self.adjacent_to_unconnected_harvester),
                )
                vis("deny_ore_neighbours", DumpTiles(self.deny_ore_neighbours))
                vis("econ_disc", DumpTiles(_econ_disc_tiles(self)))
        with Scope("offense"):
            vis("offense_target", DumpTile(self.offense_target))
            vis("offense_turns", DumpScalar(self.offense_turns))
            vis("offense_launcher", DumpTile(self.offense_launcher))
            vis(
                "last_fire",
                DumpTile(self.last_fire[0] if self.last_fire else None),
            )
            vis("nearest_enemy_turret", DumpTile(self.nearest_enemy_turret))
            vis("enemy_turret_ray_tiles", DumpTiles(self.enemy_turret_ray_tiles))
            vis("friendly_turret_ray_tiles", DumpTiles(self.friendly_turret_ray_tiles))
            vis(
                "adjacent_to_enemy_launcher",
                DumpTiles(self.adjacent_to_enemy_launcher),
            )
            vis("attack_blacklist", DumpTiles(self.attack_tile_blacklist.keys()))
        with Scope("resources"):
            vis("ti", DumpScalar(self.ti))
            vis("ax", DumpScalar(self.ax))
        with Scope("misc"):
            vis("repair_pos", DumpTile(self.repair_pos))
            vis("repaired_prev", DumpScalar(self.repaired_prev))
            vis("explore_target", DumpTile(self.explore_target))
            vis(
                "explore_heading",
                DumpScalar(
                    None
                    if self.explore_heading is None
                    else f"({self.explore_heading[0]},{self.explore_heading[1]})",
                ),
            )
            vis("opportunistic", DumpScalar(self.opportunistic))
            vis("patrol_head", DumpTile(self.patrol_head))
            patrol_age: list[float] = [-1.0] * (w * h)
            last_seen_grid: list[int] = [0] * (w * h)
            crnd = self.round
            for y in range(h):
                base = y * MAX_WIDTH
                row_base = y * w
                for x in range(w):
                    seen = self.last_seen[base + x]
                    last_seen_grid[row_base + x] = seen
                    patrol_age[row_base + x] = float(crnd - seen)
            vis(
                "patrol_age",
                DumpF32Grid(data=patrol_age, palette=P_PATROL),
            )
            vis(
                "last_seen",
                DumpI16Grid(data=last_seen_grid, palette=P_DIST),
            )
            best_age = -1
            best_dist = 1 << 30
            best_pos = None
            mx, my_y = self.my_pos.x, self.my_pos.y
            candidates = list(self.my_harvesters) + list(self.my_foundries)
            if self.my_core is not None:
                candidates.append(self.my_core)
            for p in candidates:
                age = crnd - self.last_seen[p.y * MAX_WIDTH + p.x]
                if age < best_age:
                    continue
                dxv = p.x - mx
                dyv = p.y - my_y
                d = dxv * dxv + dyv * dyv
                if age > best_age or d < best_dist:
                    best_age = age
                    best_dist = d
                    best_pos = p
            vis("patrol_target", DumpTile(best_pos))
            vis("reflect_queue_len", DumpScalar(len(self.reflect_queue)))
            vis("nearby_buildings", DumpScalar(len(self.nearby_buildings)))
            vis("healable_buildings", DumpTiles(self.healable_buildings))
