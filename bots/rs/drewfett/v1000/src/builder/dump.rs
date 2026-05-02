//! Per-turn state dump. Adds vis nodes to the debug tree under nested
//! `Scope` categories (terrain, routability, distances, econ, offense,
//! identity, resources, misc). Every value is wrapped in a `Dump*` typed
//! payload so the renderer knows exactly how to display it.

use std::collections::HashSet;

use cambc::{Controller, Position};

use crate::builder::Builder;
use crate::util::constants::{INF, STRIDE};
use crate::util::debug::{Scope, vis};
use crate::util::posint::{dist_sq, idx_of, pos_of};
use crate::util::visualiser::{Colour, Dump, Palette, PaletteStop, ScalarValue, TRANSPARENT};

// Palette factory helpers. Use `Palette::new(stops)` then assign
// `.special` rather than `Palette { stops, special }` struct literals:
// pyrust translates the literal to `Palette(stops=..., special=...)`
// which fails — the generated `__init__` only accepts `stops`.

fn p_fog() -> Palette<bool> {
    Palette::new(vec![
        PaletteStop { t: false, colour: TRANSPARENT },
        PaletteStop { t: true, colour: Colour::new(0, 0, 0, 180) },
    ])
}

fn p_cost() -> Palette<i64> {
    let mut p = Palette::new(vec![
        PaletteStop { t: 0, colour: Colour::new(50, 200, 50, 140) },
        PaletteStop { t: 100, colour: Colour::new(200, 50, 50, 140) },
    ]);
    p.special = vec![(-1, TRANSPARENT)];
    p
}

fn p_dist() -> Palette<i64> {
    let mut p = Palette::new(vec![
        PaletteStop { t: 0, colour: Colour::new(50, 240, 50, 140) },
        PaletteStop { t: 36, colour: Colour::new(240, 50, 50, 140) },
    ]);
    p.special = vec![(i64::from(INF), TRANSPARENT), (-1, TRANSPARENT)];
    p
}

fn p_bool() -> Palette<bool> {
    Palette::new(vec![
        PaletteStop { t: false, colour: TRANSPARENT },
        PaletteStop { t: true, colour: Colour::new(120, 180, 240, 140) },
    ])
}

fn p_patrol() -> Palette<f64> {
    let mut p = Palette::new(vec![
        PaletteStop { t: 0.0, colour: Colour::new(80, 140, 220, 100) },
        PaletteStop { t: 200.0, colour: Colour::new(240, 80, 80, 200) },
    ]);
    p.special = vec![(-1.0, TRANSPARENT)];
    p
}

/// Crop a flat `MAX_WIDTH` x `MAX_WIDTH` array to actual map dimensions,
/// replacing INF / >=1e6 sentinels with -1 so the palette's `special`
/// table can render them as transparent.
fn _crop(arr: &[i32], w: i32, h: i32) -> Vec<i16> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * STRIDE;
        for x in 0..w {
            let c = arr[base + (x as usize)];
            pyrust::vec::push!(out, if c < 1_000_000 { c as i16 } else { -1 });
        }
    }
    out
}

fn _crop_bool(arr: &[bool], w: i32, h: i32) -> Vec<bool> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * STRIDE;
        for x in 0..w {
            pyrust::vec::push!(out, arr[base + (x as usize)]);
        }
    }
    out
}

/// Tiles inside our econ disc — eligible for ECON/DEFENSE ore claims.
fn _econ_disc_tiles(builder: &Builder) -> HashSet<Position> {
    let mut tiles: HashSet<Position> = pyrust::set::new!();
    let w = builder.state.width;
    let h = builder.state.height;
    let core_p = idx_of(builder.my_core);
    let r2 = builder.econ_radius_sq;
    for y in 0..h {
        for x in 0..w {
            let p = y * (crate::util::posint::STRIDE) + x;
            if dist_sq(p, core_p) <= r2 {
                pyrust::set::add!(tiles, pos_of(p));
            }
        }
    }
    tiles
}

fn _reach_roots(builder: &Builder, w: i32, h: i32) -> Vec<i16> {
    let parent = &builder.reach_parent;
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * STRIDE;
        for x in 0..w {
            pyrust::vec::push!(out, parent[base + (x as usize)] as i16);
        }
    }
    out
}

fn _hsv_to_rgb(h: f64, s: f64, v: f64) -> (u8, u8, u8) {
    let i = (h * 6.0) as i32;
    let f = h * 6.0 - pyrust::float!(i);
    let p = v * (1.0 - s);
    let q = v * (1.0 - s * f);
    let t = v * (1.0 - s * (1.0 - f));
    let (r, g, b) = match i% 6 {
        0 => (v, t, p),
        1 => (q, v, p),
        2 => (p, v, t),
        3 => (p, q, v),
        4 => (t, p, v),
        5 => (v, p, q),
        _ => unreachable!(),
    };
    ((r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8)
}

const _GOLDEN: f64 = 0.6180339887498949;

fn _reach_palette(builder: &Builder, w: i32, h: i32) -> Palette<i64> {
    let parent = &builder.reach_parent;
    let mut keys: Vec<i32> = pyrust::vec::new!();
    let mut seen: HashSet<i32> = pyrust::set::new!();
    for y in 0..h {
        let base = (y as usize) * STRIDE;
        for x in 0..w {
            let v = parent[base + (x as usize)];
            if v != -1 && pyrust::set::add!(seen, v) {
                pyrust::vec::push!(keys, v);
            }
        }
    }
    keys.sort();
    let mut special: Vec<(i64, Colour)> = vec![(-1, TRANSPARENT)];
    for (k, key) in pyrust::enumerate!(pyrust::iter!(keys)) {
        let hue = ((k as f64) * _GOLDEN)% 1.0;
        let (r, g, b) = _hsv_to_rgb(hue, 0.65, 0.95);
        pyrust::vec::push!(special, (i64::from(*key), Colour::new(r, g, b, 160)));
    }
    let mut p = Palette::new(vec![
        PaletteStop { t: 0, colour: TRANSPARENT },
        PaletteStop { t: 1, colour: TRANSPARENT },
    ]);
    p.special = special;
    p
}

fn vis_tile(name: &str, pos: Option<Position>) {
    vis(name, &Dump::Tile { pos });
}

fn vis_tiles<I>(name: &str, iter: I)
where
    I: IntoIterator<Item = Position>,
{
    // Sort by (y, x) so dumps are deterministic across hash-randomized
    // iteration of HashSet/HashMap source collections.
    let mut data: Vec<Position> = pyrust::collect!(pyrust::into_iter!(iter));
    pyrust::sort_by_key!(data, |p| (p.y, p.x));
    vis(name, &Dump::Tiles { data });
}

fn vis_scalar_str(name: &str, s: &str) {
    vis(
        name,
        &Dump::Scalar {
            value: ScalarValue::Str(pyrust::to_string!(s)),
        },
    );
}

fn vis_scalar_int(name: &str, v: i64) {
    vis(
        name,
        &Dump::Scalar {
            value: ScalarValue::Int(v),
        },
    );
}

fn vis_scalar_bool(name: &str, v: bool) {
    vis(
        name,
        &Dump::Scalar {
            value: ScalarValue::Bool(v),
        },
    );
}

fn vis_scalar_null(name: &str) {
    vis(
        name,
        &Dump::Scalar {
            value: ScalarValue::Null,
        },
    );
}

pub fn dump(builder: &mut Builder, _ct: &mut Controller<'_>) {
    let w = builder.state.width;
    let h = builder.state.height;
    let _g = Scope::new("dump");
    {
        let _g = Scope::new("identity");
        vis_scalar_int("id", i64::from(builder.state.my_id));
        vis_tile("pos", Some(builder.state.my_pos));
        vis_scalar_int("round", i64::from(builder.state.round));
        match builder.role {
            Some(r) => vis_scalar_str("role", &format!("{r}")),
            None => vis_scalar_null("role"),
        }
        vis_scalar_int("role_age", i64::from(builder.role_age));
        match builder.symmetry {
            Some(s) => vis_scalar_str("symmetry", &format!("{s}")),
            None => vis_scalar_null("symmetry"),
        }
        let mut sym_names: Vec<String> = pyrust::collect!(pyrust::map!(
            pyrust::iter!(builder.state.symmetry_candidates),
            |s| format!("{s}")
        ));
        sym_names.sort();
        // Manual join — pyrust translates `Vec::join` to Python `list.join`
        // which doesn't exist (Python uses `str.join(list)` instead).
        let mut joined: String = pyrust::string::new!();
        for (i, s) in pyrust::enumerate!(pyrust::iter!(sym_names)) {
            if i > 0 {
                joined += ", ";
            }
            joined += s;
        }
        vis_scalar_str("symmetry_candidates", &joined);
        vis_scalar_bool("en_core_seen", builder.en_core_seen);
        vis(
            "bugnav_path",
            &Dump::Path {
                points: builder.bugnav.committed_positions(),
                colour: Colour::new(0, 200, 0, 180),
            },
        );
        vis(
            "bugnav_goal",
            &Dump::Dot {
                pos: builder.bugnav.active_goal,
                colour: Colour::new(255, 50, 50, 220),
            },
        );
        vis_scalar_bool("bugnav_gen_done", builder.bugnav.gen_done);
        vis_scalar_bool("bugnav_unreachable", builder.bugnav.unreachable);
        vis(
            "bugnav_mline",
            &Dump::Path {
                points: builder.bugnav.mline(),
                colour: Colour::new(255, 200, 0, 180),
            },
        );
    }
    {
        let _g = Scope::new("terrain");
        let mut unseen: Vec<bool> = Vec::with_capacity((w * h) as usize);
        for y in 0..h {
            for x in 0..w {
                pyrust::vec::push!(
                    unseen,
                    pyrust::is_none!(builder.env[(y as usize) * STRIDE + (x as usize)])
                );
            }
        }
        vis(
            "unseen",
            &Dump::BoolGrid {
                data: unseen,
                palette: p_fog(),
            },
        );
        vis(
            "cost",
            &Dump::I16Grid {
                data: _crop(&builder.cost_grid, w, h),
                palette: p_cost(),
            },
        );
        vis(
            "buildable",
            &Dump::BoolGrid {
                data: _crop_bool(&builder.buildable, w, h),
                palette: p_bool(),
            },
        );
    }
    {
        let _g = Scope::new("routability");
        vis(
            "ti_routable",
            &Dump::BoolGrid {
                data: _crop_bool(&builder.ti_routable, w, h),
                palette: p_bool(),
            },
        );
        vis(
            "ax_routable",
            &Dump::BoolGrid {
                data: _crop_bool(&builder.ax_routable, w, h),
                palette: p_bool(),
            },
        );
        vis(
            "ti_leakage",
            &Dump::BoolGrid {
                data: _crop_bool(&builder.ti_leakage, w, h),
                palette: p_bool(),
            },
        );
        vis(
            "ax_leakage",
            &Dump::BoolGrid {
                data: _crop_bool(&builder.ax_leakage, w, h),
                palette: p_bool(),
            },
        );
    }
    {
        let _g = Scope::new("distances");
        vis(
            "reach_root",
            &Dump::I16Grid {
                data: _reach_roots(builder, w, h),
                palette: _reach_palette(builder, w, h),
            },
        );
        vis(
            "ti_conv_dist",
            &Dump::I16Grid {
                data: _crop(&builder.conv_search._dist, w, h),
                palette: p_dist(),
            },
        );
        vis(
            "ax_conv_dist",
            &Dump::I16Grid {
                data: _crop(&builder.ax_conv_search._dist, w, h),
                palette: p_dist(),
            },
        );
    }
    {
        let _g = Scope::new("econ");
        {
            let _g = Scope::new("targets");
            vis_tile("ti_ore_target", builder.ore_target);
            vis_tile("ax_ore_target", builder.ax_ore_target);
            vis_tile("offensive_ore_target", builder.offensive_ore_target);
            vis_tile("foundry_target", builder.foundry_target);
            vis_tile("ti_sink", builder.ti_sink);
            vis_tile("ax_sink", builder.ax_sink);
            vis_tile("dangling_output", builder.dangling_output);
        }
        {
            let _g = Scope::new("sets");
            vis_tiles(
                "dangling_set",
                pyrust::map!(pyrust::iter!(builder.dangling_set), |p| pos_of(*p)),
            );
            vis_tiles(
                "unreachable_dangling",
                pyrust::map!(pyrust::iter!(builder.unreachable_dangling), |p| pos_of(*p)),
            );
            vis_tiles(
                "reaches_core",
                pyrust::map!(pyrust::iter!(builder.reaches_core), |p| pos_of(*p)),
            );
            vis_tiles(
                "reaches_foundry",
                pyrust::map!(pyrust::iter!(builder.reaches_foundry), |p| pos_of(*p)),
            );
            vis_tiles(
                "ti_upstream",
                pyrust::map!(pyrust::iter!(builder.ti_upstream), |p| pos_of(*p)),
            );
            vis_tiles(
                "ax_upstream",
                pyrust::map!(pyrust::iter!(builder.ax_upstream), |p| pos_of(*p)),
            );
            vis_tiles(
                "upstream_of_dangling",
                pyrust::map!(pyrust::iter!(builder.upstream_of_dangling), |p| pos_of(*p)),
            );
            vis_tiles(
                "upstream_of_congestion",
                pyrust::map!(pyrust::iter!(builder.upstream_of_congestion), |p| pos_of(*p)),
            );
            vis_tiles(
                "junctions",
                pyrust::map!(pyrust::iter!(builder.junctions), |p| pos_of(*p)),
            );
            vis_tiles(
                "is_multi_input",
                pyrust::map!(pyrust::iter!(builder.is_multi_input), |p| pos_of(*p)),
            );
            vis_tiles(
                "congested_junctions",
                pyrust::map!(pyrust::iter!(builder.congested_junctions), |p| pos_of(*p)),
            );
            vis_tiles(
                "my_foundries",
                pyrust::map!(pyrust::iter!(builder.my_foundries), |p| pos_of(*p)),
            );
        }
        {
            let _g = Scope::new("harvesters");
            vis_tiles(
                "ti_harvester_adjacent",
                pyrust::map!(pyrust::iter!(builder.ti_harvester_adjacent), |p| pos_of(*p)),
            );
            vis_tiles(
                "ax_harvester_adjacent",
                pyrust::map!(pyrust::iter!(builder.ax_harvester_adjacent), |p| pos_of(*p)),
            );
            vis_tiles(
                "harvester_adjacent",
                pyrust::map!(pyrust::iter!(builder.adjacent_to_harvester), |p| pos_of(*p)),
            );
            vis_tiles(
                "unconnected_harvester",
                pyrust::map!(pyrust::iter!(builder.adjacent_to_unconnected_harvester), |p| pos_of(*p)),
            );
            vis_tiles(
                "deny_ore_neighbours",
                pyrust::map!(pyrust::iter!(builder.deny_ore_neighbours), |p| pos_of(*p)),
            );
            vis_tiles("econ_disc", _econ_disc_tiles(builder));
        }
    }
    {
        let _g = Scope::new("offense");
        vis_tile("offense_target", builder.offense_target);
        vis_scalar_int("offense_turns", i64::from(builder.offense_turns));
        vis_tile("offense_launcher", builder.offense_launcher);
        // pyrust::map! on Option emits `(t[0] for t in opt)` which crashes
        // on None at runtime. Unwrap with `if let Some` instead.
        let last_fire_pos = if let Some(t) = builder.last_fire {
            Some(t.0)
        } else {
            None
        };
        vis_tile("last_fire", last_fire_pos);
        vis_tile("nearest_enemy_turret", builder.nearest_enemy_turret);
        vis_tiles(
            "enemy_turret_ray_tiles",
            pyrust::map!(pyrust::iter!(builder.enemy_turret_ray_tiles), |p| pos_of(*p)),
        );
        vis_tiles(
            "friendly_turret_ray_tiles",
            pyrust::map!(pyrust::iter!(builder.friendly_turret_ray_tiles), |p| pos_of(*p)),
        );
        vis_tiles(
            "adjacent_to_enemy_launcher",
            pyrust::map!(pyrust::iter!(builder.adjacent_to_enemy_launcher), |p| pos_of(*p)),
        );
        vis_tiles(
            "attack_blacklist",
            pyrust::map!(builder.attack_tile_blacklist.keys(), |p| pos_of(*p)),
        );
    }
    {
        let _g = Scope::new("resources");
        vis_scalar_int("ti", i64::from(builder.state.ti));
        vis_scalar_int("ax", i64::from(builder.state.ax));
    }
    {
        let _g = Scope::new("misc");
        vis_tile("repair_pos", builder.repair_pos);
        vis_scalar_bool("repaired_prev", builder.repaired_prev);
        vis_tile("explore_target", builder.explore_target);
        match builder.explore_heading {
            Some((x, y)) => vis_scalar_str("explore_heading", &format!("({x},{y})")),
            None => vis_scalar_null("explore_heading"),
        }
        vis_scalar_bool("opportunistic", builder.opportunistic);
        vis_tile("patrol_head", builder.patrol_head);
        let mut patrol_age: Vec<f32> = vec![-1.0; (w * h) as usize];
        let mut last_seen_grid: Vec<i16> = vec![0; (w * h) as usize];
        let crnd = builder.state.round;
        for y in 0..h {
            let base = (y as usize) * STRIDE;
            let row_base = (y * w) as usize;
            for x in 0..w {
                let seen = builder.last_seen[base + (x as usize)];
                last_seen_grid[row_base + (x as usize)] = seen as i16;
                patrol_age[row_base + (x as usize)] = (crnd - seen) as f32;
            }
        }
        vis(
            "patrol_age",
            &Dump::F32Grid {
                data: patrol_age,
                palette: p_patrol(),
            },
        );
        vis(
            "last_seen",
            &Dump::I16Grid {
                data: last_seen_grid,
                palette: p_dist(),
            },
        );
        let mut best_age: i32 = -1;
        let mut best_dist: i32 = 1 << 30;
        let mut best_pos: Option<Position> = None;
        let mx = builder.state.my_pos.x;
        let my_y = builder.state.my_pos.y;
        let mut candidates: Vec<Position> = pyrust::collect!(pyrust::map!(
            pyrust::iter!(builder.my_harvesters),
            |p| pos_of(*p)
        ));
        pyrust::vec::extend!(
            candidates,
            pyrust::map!(pyrust::iter!(builder.my_foundries), |p| pos_of(*p))
        );
        pyrust::vec::push!(candidates, builder.my_core);
        for p in &candidates {
            let age = crnd - builder.last_seen[(p.y as usize) * STRIDE + (p.x as usize)];
            if age < best_age {
                continue;
            }
            let dxv = p.x - mx;
            let dyv = p.y - my_y;
            let d = dxv * dxv + dyv * dyv;
            if age > best_age || d < best_dist {
                best_age = age;
                best_dist = d;
                best_pos = Some(*p);
            }
        }
        vis_tile("patrol_target", best_pos);
        vis_scalar_int(
            "reflect_queue_len",
            pyrust::len!(builder.reflect_queue) as i64,
        );
        vis_scalar_int(
            "nearby_buildings",
            pyrust::len!(builder.nearby_buildings) as i64,
        );
        vis_tiles(
            "healable_buildings",
            pyrust::copied!(pyrust::iter!(builder.healable_buildings)),
        );
    }
}
