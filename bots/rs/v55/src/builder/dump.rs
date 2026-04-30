//! Per-turn state dump. Adds vis nodes to the debug tree under nested
//! `Scope` categories (terrain, routability, distances, econ, offense,
//! identity, resources, misc). Every value is wrapped in a `Dump*` typed
//! payload so the renderer knows exactly how to display it.

use std::collections::HashSet;

use cambc::{Controller, Position};

use crate::builder::Builder;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::debug::{Scope, vis};
use crate::util::visualiser::{Colour, Dump, Palette, PaletteStop, ScalarValue, TRANSPARENT};

fn p_fog() -> Palette<bool> {
    Palette {
        stops: vec![
            PaletteStop {
                t: false,
                colour: TRANSPARENT,
            },
            PaletteStop {
                t: true,
                colour: Colour::new(0, 0, 0, 180),
            },
        ],
        special: Vec::new(),
    }
}

fn p_cost() -> Palette<i64> {
    Palette {
        stops: vec![
            PaletteStop {
                t: 0,
                colour: Colour::new(50, 200, 50, 140),
            },
            PaletteStop {
                t: 100,
                colour: Colour::new(200, 50, 50, 140),
            },
        ],
        special: vec![(-1, TRANSPARENT)],
    }
}

fn p_dist() -> Palette<i64> {
    Palette {
        stops: vec![
            PaletteStop {
                t: 0,
                colour: Colour::new(50, 240, 50, 140),
            },
            PaletteStop {
                t: 36,
                colour: Colour::new(240, 50, 50, 140),
            },
        ],
        special: vec![(INF as i64, TRANSPARENT), (-1, TRANSPARENT)],
    }
}

fn p_bool() -> Palette<bool> {
    Palette {
        stops: vec![
            PaletteStop {
                t: false,
                colour: TRANSPARENT,
            },
            PaletteStop {
                t: true,
                colour: Colour::new(120, 180, 240, 140),
            },
        ],
        special: Vec::new(),
    }
}

fn p_patrol() -> Palette<f64> {
    Palette {
        stops: vec![
            PaletteStop {
                t: 0.0,
                colour: Colour::new(80, 140, 220, 100),
            },
            PaletteStop {
                t: 200.0,
                colour: Colour::new(240, 80, 80, 200),
            },
        ],
        special: vec![(-1.0, TRANSPARENT)],
    }
}

/// Crop a flat MAX_WIDTH x MAX_WIDTH array to actual map dimensions,
/// replacing INF / >=1e6 sentinels with -1 so the palette's `special`
/// table can render them as transparent.
fn _crop(arr: &[i32], w: i32, h: i32) -> Vec<i16> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            let c = arr[base + (x as usize)];
            out.push(if c < 1_000_000 { c as i16 } else { -1 });
        }
    }
    out
}

fn _crop_bool(arr: &[bool], w: i32, h: i32) -> Vec<bool> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            out.push(arr[base + (x as usize)]);
        }
    }
    out
}

/// Tiles inside our econ disc — eligible for ECON/DEFENSE ore claims.
fn _econ_disc_tiles(builder: &Builder) -> HashSet<Position> {
    let mut tiles: HashSet<Position> = HashSet::new();
    let w = builder.state.width;
    let h = builder.state.height;
    let core = builder.my_core;
    let r2 = builder.econ_radius_sq;
    for y in 0..h {
        for x in 0..w {
            let p = Position { x, y };
            if p.distance_squared(core) <= r2 {
                tiles.insert(p);
            }
        }
    }
    tiles
}

fn _reach_roots(builder: &Builder, w: i32, h: i32) -> Vec<i16> {
    let parent = &builder.reach_parent;
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            out.push(parent[base + (x as usize)] as i16);
        }
    }
    out
}

fn _hsv_to_rgb(h: f64, s: f64, v: f64) -> (u8, u8, u8) {
    let i = (h * 6.0) as i32;
    let f = h * 6.0 - i as f64;
    let p = v * (1.0 - s);
    let q = v * (1.0 - s * f);
    let t = v * (1.0 - s * (1.0 - f));
    let (r, g, b) = match i.rem_euclid(6) {
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
    let mut keys: Vec<i32> = Vec::new();
    let mut seen: HashSet<i32> = HashSet::new();
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            let v = parent[base + (x as usize)];
            if v != -1 && seen.insert(v) {
                keys.push(v);
            }
        }
    }
    keys.sort_unstable();
    let mut special: Vec<(i64, Colour)> = vec![(-1, TRANSPARENT)];
    for (k, key) in keys.iter().enumerate() {
        let hue = ((k as f64) * _GOLDEN).rem_euclid(1.0);
        let (r, g, b) = _hsv_to_rgb(hue, 0.65, 0.95);
        special.push((*key as i64, Colour::new(r, g, b, 160)));
    }
    Palette {
        stops: vec![
            PaletteStop {
                t: 0,
                colour: TRANSPARENT,
            },
            PaletteStop {
                t: 1,
                colour: TRANSPARENT,
            },
        ],
        special,
    }
}

fn vis_tile(name: &str, pos: Option<Position>) {
    vis(name, &Dump::Tile { pos });
}

fn vis_tiles<I>(name: &str, iter: I)
where
    I: IntoIterator<Item = Position>,
{
    let data: Vec<Position> = iter.into_iter().collect();
    vis(name, &Dump::Tiles { data });
}

fn vis_scalar_str(name: &str, s: &str) {
    vis(
        name,
        &Dump::Scalar {
            value: ScalarValue::Str(s.to_string()),
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
        vis_scalar_int("id", builder.state.my_id as i64);
        vis_tile("pos", Some(builder.state.my_pos));
        vis_scalar_int("round", builder.state.round as i64);
        match builder.role {
            Some(r) => vis_scalar_str("role", &format!("{r}")),
            None => vis_scalar_null("role"),
        }
        vis_scalar_int("role_age", builder.role_age as i64);
        match builder.symmetry() {
            Some(s) => vis_scalar_str("symmetry", &format!("{s}")),
            None => vis_scalar_null("symmetry"),
        }
        let mut sym_names: Vec<String> = builder
            .state
            .symmetry_candidates
            .iter()
            .map(|s| format!("{s}"))
            .collect();
        sym_names.sort();
        vis_scalar_str("symmetry_candidates", &sym_names.join(", "));
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
                pos: builder.bugnav.active_goal(),
                colour: Colour::new(255, 50, 50, 220),
            },
        );
        vis_scalar_bool("bugnav_gen_done", builder.bugnav.gen_done());
        vis_scalar_bool("bugnav_unreachable", builder.bugnav.unreachable());
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
                unseen.push(builder.env[(y as usize) * MAX_WIDTH + (x as usize)].is_none());
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
            vis_tiles("dangling_set", builder.dangling_set.iter().copied());
            vis_tiles(
                "unreachable_dangling",
                builder.unreachable_dangling.iter().copied(),
            );
            vis_tiles("reaches_core", builder.reaches_core.iter().copied());
            vis_tiles("reaches_foundry", builder.reaches_foundry.iter().copied());
            vis_tiles("ti_upstream", builder.ti_upstream.iter().copied());
            vis_tiles("ax_upstream", builder.ax_upstream.iter().copied());
            vis_tiles(
                "upstream_of_dangling",
                builder.upstream_of_dangling.iter().copied(),
            );
            vis_tiles(
                "upstream_of_congestion",
                builder.upstream_of_congestion.iter().copied(),
            );
            vis_tiles("junctions", builder.junctions.iter().copied());
            vis_tiles("is_multi_input", builder.is_multi_input.iter().copied());
            vis_tiles(
                "congested_junctions",
                builder.congested_junctions.iter().copied(),
            );
            vis_tiles("my_foundries", builder.my_foundries.iter().copied());
        }
        {
            let _g = Scope::new("harvesters");
            vis_tiles(
                "ti_harvester_adjacent",
                builder.ti_harvester_adjacent.iter().copied(),
            );
            vis_tiles(
                "ax_harvester_adjacent",
                builder.ax_harvester_adjacent.iter().copied(),
            );
            vis_tiles(
                "harvester_adjacent",
                builder.adjacent_to_harvester.iter().copied(),
            );
            vis_tiles(
                "unconnected_harvester",
                builder.adjacent_to_unconnected_harvester.iter().copied(),
            );
            vis_tiles(
                "deny_ore_neighbours",
                builder.deny_ore_neighbours.iter().copied(),
            );
            vis_tiles("econ_disc", _econ_disc_tiles(builder));
        }
    }
    {
        let _g = Scope::new("offense");
        vis_tile("offense_target", builder.offense_target);
        vis_scalar_int("offense_turns", builder.offense_turns as i64);
        vis_tile("offense_launcher", builder.offense_launcher);
        vis_tile("last_fire", builder.last_fire.map(|(p, _)| p));
        vis_tile("nearest_enemy_turret", builder.nearest_enemy_turret);
        vis_tiles(
            "enemy_turret_ray_tiles",
            builder.enemy_turret_ray_tiles.iter().copied(),
        );
        vis_tiles(
            "friendly_turret_ray_tiles",
            builder.friendly_turret_ray_tiles.iter().copied(),
        );
        vis_tiles(
            "adjacent_to_enemy_launcher",
            builder.adjacent_to_enemy_launcher.iter().copied(),
        );
        vis_tiles(
            "attack_blacklist",
            builder.attack_tile_blacklist.keys().copied(),
        );
    }
    {
        let _g = Scope::new("resources");
        vis_scalar_int("ti", builder.state.ti as i64);
        vis_scalar_int("ax", builder.state.ax as i64);
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
            let base = (y as usize) * MAX_WIDTH;
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
        let mut candidates: Vec<Position> = builder.my_harvesters.iter().copied().collect();
        candidates.extend(builder.my_foundries.iter().copied());
        candidates.push(builder.my_core);
        for p in &candidates {
            let age = crnd - builder.last_seen[(p.y as usize) * MAX_WIDTH + (p.x as usize)];
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
        vis_scalar_int("reflect_queue_len", builder.reflect_queue.len() as i64);
        vis_scalar_int("nearby_buildings", builder.nearby_buildings.len() as i64);
        vis_tiles(
            "healable_buildings",
            builder.healable_buildings.iter().copied(),
        );
    }
}
