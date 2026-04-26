"""Per-turn state dump. Adds vis nodes to the debug tree under nested
`Scope` categories (terrain, routability, distances, econ, offense,
identity, resources, misc). Scalars use the auto-tagged path; grids
and tile-sets use the visualiser primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH
from util.debug import Scope, vis
from visualiser import (
    TRANSPARENT,
    BoolGrid,
    Colour,
    I16Grid,
    Palette,
    PaletteStop,
    Tiles,
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
    table can render them as transparent."""
    return [
        c if c < 1e6 else -1
        for y in range(h)
        for c in arr[y * MAX_WIDTH : y * MAX_WIDTH + w]
    ]


def _crop_bool(arr: list[bool], w: int, h: int) -> list[bool]:
    return [arr[y * MAX_WIDTH + x] for y in range(h) for x in range(w)]


def _tiles(positions: Iterable[Position]) -> Tiles:
    return Tiles([(p.x, p.y) for p in positions])


def dump(self: Builder, _ct: Controller) -> None:
    w, h = self.w, self.h
    env = self.env
    with Scope("dump"):
        with Scope("identity"):
            vis("id", self.my_id)
            vis("pos", self.my_pos)
            vis("round", self.round)
            vis("role", str(self.role))
            vis("role_age", self.role_age)
            vis("permanent_role", self.permanent_role)
            vis("symmetry", self.symmetry)
            vis("symmetry_candidates", sorted(s.name for s in self.symmetry_candidates))
            vis("en_core_seen", self.en_core_seen)
        with Scope("terrain"):
            vis(
                "unseen",
                BoolGrid(
                    [
                        e is None
                        for y in range(h)
                        for e in env[y * MAX_WIDTH : y * MAX_WIDTH + w]
                    ],
                    palette=P_FOG,
                ),
            )
            vis("cost", I16Grid(_crop(self.cost_grid, w, h), palette=P_COST))
            vis("buildable", BoolGrid(_crop_bool(self.buildable, w, h), palette=P_BOOL))
        with Scope("routability"):
            vis(
                "ti_routable",
                BoolGrid(_crop_bool(self.ti_routable, w, h), palette=P_BOOL),
            )
            vis(
                "ax_routable",
                BoolGrid(_crop_bool(self.ax_routable, w, h), palette=P_BOOL),
            )
            vis(
                "ti_leakage",
                BoolGrid(_crop_bool(self.ti_leakage, w, h), palette=P_BOOL),
            )
            vis(
                "ax_leakage",
                BoolGrid(_crop_bool(self.ax_leakage, w, h), palette=P_BOOL),
            )
        with Scope("distances"):
            vis("bfs_dist", I16Grid(_crop(self.bfs_dist, w, h), palette=P_DIST))
            vis(
                "move_dist",
                I16Grid(_crop(self.move_search.dist, w, h), palette=P_DIST),
            )
            vis(
                "ti_conv_dist",
                I16Grid(_crop(self.conv_search._dist, w, h), palette=P_DIST),
            )
            vis(
                "ax_conv_dist",
                I16Grid(_crop(self.ax_conv_search._dist, w, h), palette=P_DIST),
            )
        with Scope("econ"):
            with Scope("targets"):
                vis("ti_ore_target", self.ore_target)
                vis("ax_ore_target", self.ax_ore_target)
                vis("offensive_ore_target", self.offensive_ore_target)
                vis("foundry_target", self.foundry_target)
                vis("ti_sink", self.ti_sink)
                vis("ax_sink", self.ax_sink)
                vis("dangling_output", self.dangling_output)
            with Scope("sets"):
                vis("dangling_set", _tiles(self.dangling_set))
                vis("unreachable_dangling", _tiles(self.unreachable_dangling))
                vis("reaches_core", _tiles(self.reaches_core))
                vis("reaches_foundry", _tiles(self.reaches_foundry))
                vis("ti_upstream", _tiles(self.ti_upstream))
                vis("ax_upstream", _tiles(self.ax_upstream))
                vis("upstream_of_dangling", _tiles(self.upstream_of_dangling))
                vis("upstream_of_congestion", _tiles(self.upstream_of_congestion))
                vis("junctions", _tiles(self.junctions))
                vis("is_multi_input", _tiles(self.is_multi_input))
                vis("congested_junctions", _tiles(self.congested_junctions))
                vis("my_foundries", _tiles(self.my_foundries))
            with Scope("harvesters"):
                vis("ti_harvester_adjacent", _tiles(self.ti_harvester_adjacent))
                vis("ax_harvester_adjacent", _tiles(self.ax_harvester_adjacent))
                vis("harvester_adjacent", _tiles(self.adjacent_to_harvester))
                vis(
                    "unconnected_harvester",
                    _tiles(self.adjacent_to_unconnected_harvester),
                )
                vis("deny_ore_neighbours", _tiles(self.deny_ore_neighbours))
        with Scope("offense"):
            vis("offense_target", self.offense_target)
            vis("offense_turns", self.offense_turns)
            vis("offense_launcher", self.offense_launcher)
            vis("last_fire", self.last_fire)
            vis("nearest_enemy_turret", self.nearest_enemy_turret)
            vis("enemy_turret_ray_tiles", _tiles(self.enemy_turret_ray_tiles))
            vis("friendly_turret_ray_tiles", _tiles(self.friendly_turret_ray_tiles))
            vis("adjacent_to_enemy_launcher", _tiles(self.adjacent_to_enemy_launcher))
            vis("attack_blacklist", _tiles(self.attack_tile_blacklist.keys()))
        with Scope("resources"):
            vis("ti", self.ti)
            vis("ax", self.ax)
        with Scope("misc"):
            vis("repair_pos", self.repair_pos)
            vis("repaired_prev", self.repaired_prev)
            vis("scout_target", self.scout_target)
            vis("scout_age", self.scout_age)
            vis("opportunistic", self.opportunistic)
            vis("patrol_head", self.patrol_head)
            vis("patrol_trail", _tiles(self.patrol_trail))
            vis("reflect_queue_len", len(self.reflect_queue))
            vis("nearby_buildings", len(self.nearby_buildings))
            vis("healable_buildings", _tiles(self.healable_buildings))
