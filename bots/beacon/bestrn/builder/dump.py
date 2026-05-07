"""
Per-turn state dump. Adds vis nodes to the debug tree under nested
`Scope` categories (terrain, routability, distances, econ, offense,
identity, resources, misc). Every value is wrapped in a `Dump*` typed
payload so the renderer knows exactly how to display it.
"""

from __future__ import annotations

from typing import Final

from cambc import Position
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller
if TYPE_CHECKING:
    from builder import Builder
from util.constants import INF, MAX_WIDTH
from util.debug import Scope, vis
from util.visualiser import (
    Colour,
    Dump,
    Palette,
    PaletteStop,
    ScalarValue,
    TRANSPARENT,
    DumpI16Grid,
    DumpTiles,
    DumpTile,
    DumpDot,
    DumpPath,
    DumpScalar,
    ScalarValueInt,
    ScalarValueBool,
    ScalarValueStr,
    ScalarValueNull,
)

if TYPE_CHECKING:
    from util.visualiser import (
        DumpBoolGrid,
        DumpU8Grid,
        DumpU16Grid,
        DumpF32Grid,
        DumpVectorField,
        ScalarValueFloat,
    )


def p_fog():
    return Palette(
        stops=[
            PaletteStop(t=False, colour=TRANSPARENT),
            PaletteStop(t=True, colour=Colour(0, 0, 0, 180)),
        ],
        special=[],
    )


def p_cost():
    return Palette(
        stops=[
            PaletteStop(t=0, colour=Colour(50, 200, 50, 140)),
            PaletteStop(t=100, colour=Colour(200, 50, 50, 140)),
        ],
        special=[(-1, TRANSPARENT)],
    )


def p_dist():
    return Palette(
        stops=[
            PaletteStop(t=0, colour=Colour(50, 240, 50, 140)),
            PaletteStop(t=36, colour=Colour(240, 50, 50, 140)),
        ],
        special=[(int(1000000), TRANSPARENT), (-1, TRANSPARENT)],
    )


def p_bool():
    return Palette(
        stops=[
            PaletteStop(t=False, colour=TRANSPARENT),
            PaletteStop(t=True, colour=Colour(120, 180, 240, 140)),
        ],
        special=[],
    )


def p_patrol():
    return Palette(
        stops=[
            PaletteStop(t=0.0, colour=Colour(80, 140, 220, 100)),
            PaletteStop(t=200.0, colour=Colour(240, 80, 80, 200)),
        ],
        special=[(-1.0, TRANSPARENT)],
    )


def _crop(arr, w, h):
    """
    Crop a flat `MAX_WIDTH` x `MAX_WIDTH` array to actual map dimensions,
    replacing INF / >=1e6 sentinels with -1 so the palette's `special`
    table can render them as transparent.
    """
    out = []
    for y in range(0, h):
        base = int(y) * 50
        for x in range(0, w):
            c = arr[base + int(x)]
            out.append(int(c) if c < 1000000 else -1)
    return out


def _crop_bool(arr, w, h):
    out = []
    for y in range(0, h):
        base = int(y) * 50
        for x in range(0, w):
            out.append(arr[base + int(x)])
    return out


def _econ_disc_tiles(builder):
    """Tiles inside our econ disc — eligible for ECON/DEFENSE ore claims."""
    tiles: set[Position] = set()
    w = builder.state.width
    h = builder.state.height
    core = builder.my_core
    r2 = builder.econ_radius_sq
    for y in range(0, h):
        for x in range(0, w):
            p = Position(x=x, y=y)
            if p.distance_squared(core) <= r2:
                tiles.add(p)
    return tiles


def _reach_roots(builder, w, h):
    parent = builder.reach_parent
    out = []
    for y in range(0, h):
        base = int(y) * 50
        for x in range(0, w):
            out.append(int(parent[base + int(x)]))
    return out


def _hsv_to_rgb(h, s, v):
    i = int(h * 6.0)
    f = h * 6.0 + -float(i)
    p = v * (1.0 - s)
    q = v * (s * -f + 1.0)
    t = v * (s * -(1.0 - f) + 1.0)
    match (i) % (6):
        case 0:
            r, g, b = (v, t, p)
        case 1:
            r, g, b = (q, v, p)
        case 2:
            r, g, b = (p, v, t)
        case 3:
            r, g, b = (p, q, v)
        case 4:
            r, g, b = (t, p, v)
        case 5:
            r, g, b = (v, p, q)
        case _:
            r, g, b = (_ for _ in ()).throw(AssertionError("unreachable"))
    return (int(r * 255.0), int(g * 255.0), int(b * 255.0))


_GOLDEN: Final[float] = 0.6180339887498949


def _reach_palette(builder, w, h):
    parent = builder.reach_parent
    keys: list[int] = []
    seen: set[int] = set()
    for y in range(0, h):
        base = int(y) * 50
        for x in range(0, w):
            v = parent[base + int(x)]
            if v != -1 and seen.add(v):
                keys.append(v)
    keys.sort()
    special: list[tuple[int, Colour]] = [(-1, TRANSPARENT)]
    for k, key in enumerate(keys):
        hue = (float(k) * 0.6180339887498949) % (1.0)
        r, g, b = _hsv_to_rgb(hue, 0.65, 0.95)
        special.append((int(key), Colour(r, g, b, 160)))
    return Palette(
        stops=[
            PaletteStop(t=0, colour=TRANSPARENT),
            PaletteStop(t=1, colour=TRANSPARENT),
        ],
        special=special,
    )


def vis_tile(name, pos):
    vis(name, DumpTile(pos=pos))


def vis_tiles(name, iter):
    data: list[Position] = list(iter)
    data.sort(key=lambda p: (p.y, p.x))
    vis(name, DumpTiles(data=data))


def vis_scalar_str(name, s):
    vis(name, DumpScalar(value=ScalarValueStr(_0=str(s))))


def vis_scalar_int(name, v):
    vis(name, DumpScalar(value=ScalarValueInt(_0=v)))


def vis_scalar_bool(name, v):
    vis(name, DumpScalar(value=ScalarValueBool(_0=v)))


def vis_scalar_null(name):
    vis(name, DumpScalar(value=ScalarValueNull()))


def dump(builder, _ct):
    w = builder.state.width
    h = builder.state.height
    with Scope("dump") as _g:
        with Scope("identity") as _g:
            vis_scalar_int("id", int(builder.state.my_id))
            vis_tile("pos", builder.state.my_pos)
            vis_scalar_int("round", int(builder.state.round))
            match builder.role:
                case None:
                    vis_scalar_null("role")
                case r if r is not None:
                    vis_scalar_str("role", f"{r}")
            vis_scalar_int("role_age", int(builder.role_age))
            match builder.symmetry:
                case None:
                    vis_scalar_null("symmetry")
                case s if s is not None:
                    vis_scalar_str("symmetry", f"{s}")
            sym_names: list[str] = list(
                (f"{s}" for s in builder.state.symmetry_candidates)
            )
            sym_names.sort()
            vis_scalar_str("symmetry_candidates", ", ".join(sym_names))
            vis_scalar_bool("en_core_seen", builder.en_core_seen)
            vis(
                "bugnav_path",
                DumpPath(
                    points=builder.bugnav.committed_positions(),
                    colour=Colour(0, 200, 0, 180),
                ),
            )
            vis(
                "bugnav_goal",
                DumpDot(
                    pos=builder.bugnav.active_goal, colour=Colour(255, 50, 50, 220)
                ),
            )
            vis_scalar_bool("bugnav_gen_done", builder.bugnav.gen_done)
            vis_scalar_bool("bugnav_unreachable", builder.bugnav.unreachable)
            vis(
                "bugnav_mline",
                DumpPath(
                    points=builder.bugnav.mline(), colour=Colour(255, 200, 0, 180)
                ),
            )
        with Scope("distances") as _g:
            vis(
                "ax_conv_dist",
                DumpI16Grid(
                    data=_crop(builder.ax_conv_search._dist, w, h), palette=p_dist()
                ),
            )
        with Scope("econ") as _g:
            with Scope("targets") as _g:
                vis_tile("ti_ore_target", builder.ore_target)
                vis_tile("ax_ore_target", builder.ax_ore_target)
                vis_tile("offensive_ore_target", builder.offensive_ore_target)
                vis_tile("foundry_target", builder.foundry_target)
                vis_tile("ti_sink", builder.ti_sink)
                vis_tile("ax_sink", builder.ax_sink)
                vis_tile("dangling_output", builder.dangling_output)
            with Scope("sets") as _g:
                vis_tiles("dangling_set", builder.dangling_set)
                vis_tiles("unreachable_dangling", builder.unreachable_dangling)
                vis_tiles("reaches_core", builder.reaches_core)
                vis_tiles("reaches_foundry", builder.reaches_foundry)
                vis_tiles("ti_upstream", builder.ti_upstream)
                vis_tiles("ax_upstream", builder.ax_upstream)
                vis_tiles("upstream_of_dangling", builder.upstream_of_dangling)
                vis_tiles("upstream_of_congestion", builder.upstream_of_congestion)
                vis_tiles("junctions", builder.junctions)
                vis_tiles("is_multi_input", builder.is_multi_input)
                vis_tiles("congested_junctions", builder.congested_junctions)
                vis_tiles("my_foundries", builder.my_foundries)
        with Scope("offense") as _g:
            vis_tile("offense_target", builder.offense_target)
            vis_scalar_int("offense_turns", int(builder.offense_turns))
            vis_tile("offense_launcher", builder.offense_launcher)
            vis_tile(
                "last_fire",
                (
                    (lambda t: t[0])(builder.last_fire)
                    if builder.last_fire is not None
                    else None
                ),
            )
            vis_tile("nearest_enemy_turret", builder.nearest_enemy_turret)
            vis_tiles("enemy_turret_ray_tiles", builder.enemy_turret_ray_tiles)
            vis_tiles("friendly_turret_ray_tiles", builder.friendly_turret_ray_tiles)
            vis_tiles("adjacent_to_enemy_launcher", builder.adjacent_to_enemy_launcher)
            vis_tiles("attack_blacklist", builder.attack_tile_blacklist.keys())
        with Scope("resources") as _g:
            vis_scalar_int("ti", int(builder.state.ti))
            vis_scalar_int("ax", int(builder.state.ax))
        with Scope("misc") as _g:
            vis_tile("repair_pos", builder.repair_pos)
            vis_scalar_bool("repaired_prev", builder.repaired_prev)
            vis_tile("explore_target", builder.explore_target)
            match builder.explore_heading:
                case None:
                    vis_scalar_null("explore_heading")
                case (x, y):
                    vis_scalar_str("explore_heading", f"({x},{y})")
            vis_scalar_bool("opportunistic", builder.opportunistic)
            vis_tile("patrol_head", builder.patrol_head)
            crnd = builder.state.round
            best_age: int = -1
            best_dist: int = 1 << 30
            best_pos: Position | None = None
            mx = builder.state.my_pos.x
            my_y = builder.state.my_pos.y
            candidates: list[Position] = list(builder.my_harvesters)
            candidates.extend(builder.my_foundries)
            candidates.append(builder.my_core)
            for p in candidates:
                age = crnd - builder.last_seen[int(p.y) * 50 + int(p.x)]
                if age < best_age:
                    continue
                dxv = p.x - mx
                dyv = p.y - my_y
                d = dxv * dxv + dyv * dyv
                if age > best_age or d < best_dist:
                    best_age = age
                    best_dist = d
                    best_pos = p
            vis_tile("patrol_target", best_pos)
            vis_scalar_int("reflect_queue_len", int(len(builder.reflect_queue)))
            vis_scalar_int("nearby_buildings", int(len(builder.nearby_buildings)))
            vis_tiles("healable_buildings", builder.healable_buildings)
