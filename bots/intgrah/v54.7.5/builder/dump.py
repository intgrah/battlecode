"""Per-turn state dump. Adds vis nodes to the debug tree under nested
`Scope` categories (terrain, routability, distances, econ, offense,
identity, resources, misc). Every value is wrapped in a `Dump*` typed
payload so the renderer knows exactly how to display it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH
from util.debug import Scope, vis
from util.visualiser import (
    TRANSPARENT,
    Colour,
    DumpBoolGrid,
    DumpDot,
    DumpI16Grid,
    DumpPath,
    DumpScalar,
    DumpTile,
    DumpTiles,
    Palette,
    PaletteStop,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cambc import Controller, Position

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


def _crop_bool(arr: list[bool], w: int, h: int) -> list[bool]:
    return [arr[y * MAX_WIDTH + x] for y in range(h) for x in range(w)]


def _tile_or_none(p: Position | None) -> DumpScalar | DumpTile:
    return DumpScalar(None) if p is None else DumpTile(p)


def _reach_roots(self: Builder, w: int, h: int) -> list[int]:
    parent = self.reach_parent
    return [parent[y * MAX_WIDTH + x] for y in range(h) for x in range(w)]


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i %= 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)


_GOLDEN = 0.61803398875


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
                    data=_crop(self.ax_conv_search._dist, w, h), palette=P_DIST,
                ),
            )
        with Scope("econ"):
            with Scope("targets"):
                vis("ti_ore_target", _tile_or_none(self.ore_target))
                vis("ax_ore_target", _tile_or_none(self.ax_ore_target))
                vis("offensive_ore_target", _tile_or_none(self.offensive_ore_target))
                vis("foundry_target", _tile_or_none(self.foundry_target))
                vis("ti_sink", _tile_or_none(self.ti_sink))
                vis("ax_sink", _tile_or_none(self.ax_sink))
                vis("dangling_output", _tile_or_none(self.dangling_output))
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
        with Scope("offense"):
            vis("offense_target", _tile_or_none(self.offense_target))
            vis("offense_turns", DumpScalar(self.offense_turns))
            vis("offense_launcher", _tile_or_none(self.offense_launcher))
            vis(
                "last_fire",
                _tile_or_none(self.last_fire[0] if self.last_fire else None),
            )
            vis("nearest_enemy_turret", _tile_or_none(self.nearest_enemy_turret))
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
            vis("repair_pos", _tile_or_none(self.repair_pos))
            vis("repaired_prev", DumpScalar(self.repaired_prev))
            vis("explore_target", _tile_or_none(self.explore_target))
            vis(
                "explore_heading",
                DumpScalar(
                    None
                    if self.explore_heading is None
                    else f"({self.explore_heading[0]},{self.explore_heading[1]})",
                ),
            )
            vis("opportunistic", DumpScalar(self.opportunistic))
            vis("patrol_head", _tile_or_none(self.patrol_head))
            vis("patrol_trail", DumpTiles(self.patrol_trail))
            vis("reflect_queue_len", DumpScalar(len(self.reflect_queue)))
            vis("nearby_buildings", DumpScalar(len(self.nearby_buildings)))
            vis("healable_buildings", DumpTiles(self.healable_buildings))
