//! Per-turn state dump. Adds vis nodes to the debug tree under nested
//! `Scope` categories (terrain, routability, distances, econ, offense,
//! identity, resources, misc). Every value is wrapped in a `Dump*` typed
//! payload so the renderer knows exactly how to display it.

use std::collections::HashSet;

use cambc::{Controller, Position};

use crate::builder::Builder;
use crate::builder::patrol::{alert_expansion, expand_outward};
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
        special: pyrust::vec::new!(),
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
        special: vec![(i64::from(INF), TRANSPARENT), (-1, TRANSPARENT)],
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
        special: pyrust::vec::new!(),
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

/// Crop a flat `MAX_WIDTH` x `MAX_WIDTH` array to actual map dimensions,
/// replacing INF / >=1e6 sentinels with -1 so the palette's `special`
/// table can render them as transparent.
fn _crop(arr: &[i32], w: i32, h: i32) -> Vec<i16> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
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
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            pyrust::vec::push!(out, arr[base + (x as usize)]);
        }
    }
    out
}

/// Per-tile count of non-None entries in `flow_history`. Cropped to map
/// dims, returned as i16 grid for the dump.
fn _flow_volume_grid(builder: &Builder, w: i32, h: i32) -> Vec<i16> {
    let mut out = Vec::with_capacity((w * h) as usize);
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            let i = base + (x as usize);
            let v = pyrust::count!(pyrust::filter!(
                pyrust::iter!(builder.flow_history[i]),
                |t| pyrust::is_some!(t.0)
            )) as i16;
            pyrust::vec::push!(out, v);
        }
    }
    out
}

fn p_volume() -> Palette<i64> {
    Palette {
        stops: vec![
            PaletteStop {
                t: 0,
                colour: TRANSPARENT,
            },
            PaletteStop {
                t: 8,
                colour: Colour::new(240, 80, 80, 200),
            },
        ],
        special: pyrust::vec::new!(),
    }
}

/// Tiles inside our econ disc — eligible for ECON/DEFENSE ore claims.
fn _econ_disc_tiles(builder: &Builder) -> HashSet<Position> {
    let mut tiles: HashSet<Position> = pyrust::set::new!();
    let w = builder.state.width;
    let h = builder.state.height;
    let core = builder.my_core;
    let r2 = builder.econ_radius_sq;
    for y in 0..h {
        for x in 0..w {
            let p = Position { x, y };
            if p.distance_squared(core) <= r2 {
                pyrust::set::add!(tiles, p);
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
            pyrust::vec::push!(out, parent[base + (x as usize)] as i16);
        }
    }
    out
}

fn _hsv_to_rgb(h: f64, s: f64, v: f64) -> (u8, u8, u8) {
    let i = (h * 6.0) as i32;
    let f = pyrust::mul_add!(h, 6.0, -f64::from(i));
    let p = v * (1.0 - s);
    let q = v * pyrust::mul_add!(s, -f, 1.0);
    let t = v * pyrust::mul_add!(s, -(1.0 - f), 1.0);
    let (r, g, b) = match pyrust::rem_euclid!(i, 6) {
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

#[pyrust::inline]
const _GOLDEN: f64 = 0.6180339887498949;

fn _reach_palette(builder: &Builder, w: i32, h: i32) -> Palette<i64> {
    let parent = &builder.reach_parent;
    let mut keys: Vec<i32> = pyrust::vec::new!();
    let mut seen: HashSet<i32> = pyrust::set::new!();
    for y in 0..h {
        let base = (y as usize) * MAX_WIDTH;
        for x in 0..w {
            let v = parent[base + (x as usize)];
            if v != -1 && pyrust::set::add!(seen, v) {
                pyrust::vec::push!(keys, v);
            }
        }
    }
    pyrust::sort!(keys);
    let mut special: Vec<(i64, Colour)> = vec![(-1, TRANSPARENT)];
    for (k, key) in pyrust::enumerate!(pyrust::iter!(keys)) {
        let hue = pyrust::rem_euclid!(((k as f64) * _GOLDEN), 1.0);
        let (r, g, b) = _hsv_to_rgb(hue, 0.65, 0.95);
        pyrust::vec::push!(special, (i64::from(*key), Colour::new(r, g, b, 160)));
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
    pyrust::with!(Scope::new("dump"), {
        pyrust::with!(Scope::new("identity"), {
            match builder.role {
                Some(r) => vis_scalar_str("role", &format!("{r}")),
                None => vis_scalar_null("role"),
            }
            vis_scalar_int("role_age", i64::from(builder.role_age));
            vis_scalar_int("alert", i64::from(builder.alert));
            match builder.symmetry {
                Some(s) => vis_scalar_str("symmetry", &format!("{s}")),
                None => vis_scalar_null("symmetry"),
            }
            let mut sym_names: Vec<String> = pyrust::collect!(pyrust::map!(
                pyrust::iter!(builder.state.symmetry_candidates),
                |s| format!("{s}")
            ));
            sym_names.sort();
            vis_scalar_str(
                "symmetry_candidates",
                &pyrust::string::join!(", ", sym_names),
            );
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
        });
        // {
        //     let _g = Scope::new("terrain");
        //     let mut unseen: Vec<bool> = Vec::with_capacity((w * h) as usize);
        //     for y in 0..h {
        //         for x in 0..w {
        //             pyrust::vec::push!(
        //                 unseen,
        //                 pyrust::is_none!(builder.env[(y as usize) * MAX_WIDTH + (x as usize)])
        //             );
        //         }
        //     }
        //     vis(
        //         "unseen",
        //         &Dump::BoolGrid {
        //             data: unseen,
        //             palette: p_fog(),
        //         },
        //     );
        //     vis(
        //         "cost",
        //         &Dump::I16Grid {
        //             data: _crop(&builder.cost_grid, w, h),
        //             palette: p_cost(),
        //         },
        //     );
        //     vis(
        //         "buildable",
        //         &Dump::BoolGrid {
        //             data: _crop_bool(&builder.buildable, w, h),
        //             palette: p_bool(),
        //         },
        //     );
        // }
        // {
        //     let _g = Scope::new("routability");
        //     vis(
        //         "ti_routable",
        //         &Dump::BoolGrid {
        //             data: _crop_bool(&builder.ti_routable, w, h),
        //             palette: p_bool(),
        //         },
        //     );
        //     vis(
        //         "ax_routable",
        //         &Dump::BoolGrid {
        //             data: _crop_bool(&builder.ax_routable, w, h),
        //             palette: p_bool(),
        //         },
        //     );
        //     vis(
        //         "ti_leakage",
        //         &Dump::BoolGrid {
        //             data: _crop_bool(&builder.ti_leakage, w, h),
        //             palette: p_bool(),
        //         },
        //     );
        //     vis(
        //         "ax_leakage",
        //         &Dump::BoolGrid {
        //             data: _crop_bool(&builder.ax_leakage, w, h),
        //             palette: p_bool(),
        //         },
        //     );
        // }
        pyrust::with!(Scope::new("distances"), {
            // vis(
            //     "reach_root",
            //     &Dump::I16Grid {
            //         data: _reach_roots(builder, w, h),
            //         palette: _reach_palette(builder, w, h),
            //     },
            // );
            // vis(
            //     "ti_conv_dist",
            //     &Dump::I16Grid {
            //         data: _crop(&builder.conv_search._dist, w, h),
            //         palette: p_dist(),
            //     },
            // );
            vis(
                "ax_conv_dist",
                &Dump::I16Grid {
                    data: _crop(&builder.ax_conv_search._dist, w, h),
                    palette: p_dist(),
                },
            );
        });
        pyrust::with!(Scope::new("econ"), {
            pyrust::with!(Scope::new("targets"), {
                vis_tile("ti_ore_target", builder.ore_target);
                vis_tile("ax_ore_target", builder.ax_ore_target);
                vis_tile("offensive_ore_target", builder.offensive_ore_target);
                vis_tile("foundry_target", builder.foundry_target);
                vis_tile("ti_sink", builder.ti_sink);
                vis_tile("ax_sink", builder.ax_sink);
                vis_tile("dangling_output", builder.dangling_output);
            });
            pyrust::with!(Scope::new("conv_greedy"), {
                if let Some(ref pp) = builder.last_greedy_path {
                    let colour = if builder.last_greedy_path_is_ax {
                        Colour::new(200, 0, 255, 255)
                    } else {
                        Colour::new(80, 160, 255, 255)
                    };
                    vis(
                        "path",
                        &Dump::Path {
                            points: pyrust::clone!(pp),
                            colour,
                        },
                    );
                }
            });
            vis(
                "flow_volume",
                &Dump::I16Grid {
                    data: _flow_volume_grid(builder, w, h),
                    palette: p_volume(),
                },
            );
            pyrust::with!(Scope::new("sets"), {
                vis_tiles(
                    "dangling_set",
                    pyrust::copied!(pyrust::iter!(builder.dangling_set)),
                );
                vis_tiles(
                    "ti_upstream",
                    pyrust::copied!(pyrust::iter!(builder.ti_upstream)),
                );
                vis_tiles(
                    "ax_upstream",
                    pyrust::copied!(pyrust::iter!(builder.ax_upstream)),
                );
                vis_tiles(
                    "my_foundries",
                    pyrust::copied!(pyrust::iter!(builder.my_foundries)),
                );
            });
            // {
            //     let _g = Scope::new("harvesters");
            //     vis_tiles(
            //         "ti_harvester_adjacent",
            //         pyrust::copied!(pyrust::iter!(builder.ti_harvester_adjacent)),
            //     );
            //     vis_tiles(
            //         "ax_harvester_adjacent",
            //         pyrust::copied!(pyrust::iter!(builder.ax_harvester_adjacent)),
            //     );
            //     vis_tiles(
            //         "harvester_adjacent",
            //         pyrust::copied!(pyrust::iter!(builder.adjacent_to_harvester)),
            //     );
            //     vis_tiles(
            //         "unconnected_harvester",
            //         pyrust::copied!(pyrust::iter!(builder.adjacent_to_unconnected_harvester)),
            //     );
            //     vis_tiles(
            //         "deny_ore_neighbours",
            //         pyrust::copied!(pyrust::iter!(builder.deny_ore_neighbours)),
            //     );
            //     // vis_tiles("econ_disc", _econ_disc_tiles(builder));
            // }
        });
        pyrust::with!(Scope::new("offense"), {
            vis_tile("offense_target", builder.offense_target);
            vis_scalar_int("offense_turns", i64::from(builder.offense_turns));
            vis_tile("offense_launcher", builder.offense_launcher);
            vis_tile("last_fire", pyrust::opt_map!(builder.last_fire, |t| t.0));
            vis_tile("nearest_enemy_turret", builder.nearest_enemy_turret);
            vis_tiles(
                "enemy_turret_ray_tiles",
                pyrust::copied!(pyrust::iter!(builder.enemy_turret_ray_tiles)),
            );
            vis_tiles(
                "friendly_turret_ray_tiles",
                pyrust::copied!(pyrust::iter!(builder.friendly_turret_ray_tiles)),
            );
            vis_tiles(
                "adjacent_to_enemy_launcher",
                pyrust::copied!(pyrust::iter!(builder.adjacent_to_enemy_launcher)),
            );
            vis_tiles(
                "attack_blacklist",
                pyrust::copied!(builder.attack_tile_blacklist.keys()),
            );
        });
        pyrust::with!(Scope::new("misc"), {
            vis_tile("repair_pos", builder.repair_pos);
            vis_scalar_bool("repaired_prev", builder.repaired_prev);
            vis_tile("explore_target", builder.explore_target);
            match builder.explore_heading {
                Some((x, y)) => vis_scalar_str("explore_heading", &format!("({x},{y})")),
                None => vis_scalar_null("explore_heading"),
            }
            vis_scalar_bool("opportunistic", builder.opportunistic);
            let n_clusters = pyrust::len!(builder.patrol_clusters);
            if n_clusters == 0 {
                vis_tile("patrol_target", None);
            } else {
                let ci = pyrust::min!(builder.patrol_cluster_idx, n_clusters - 1);
                let cycle = &builder.patrol_clusters[ci];
                let qlen = pyrust::len!(cycle);
                if qlen > 0 {
                    let raw_target = cycle[builder.patrol_pos_idx % qlen];
                    let centroid = builder.patrol_cluster_centroids[ci];
                    let expansion = alert_expansion(builder.alert, builder.state.scale, qlen);
                    let target = expand_outward(raw_target, centroid, expansion, w, h);
                    vis_tile("patrol_target", Some(target));
                } else {
                    vis_tile("patrol_target", None);
                }
                // One Path per cluster, each closing on itself. Avoids
                // spurious edges between unrelated clusters.
                for i in 0..n_clusters {
                    let q = &builder.patrol_clusters[i];
                    if pyrust::vec::is_empty!(q) {
                        continue;
                    }
                    let qlen_i = pyrust::len!(q);
                    let centroid = builder.patrol_cluster_centroids[i];
                    let expansion = alert_expansion(builder.alert, builder.state.scale, qlen_i);
                    let mut raw: Vec<Position> = pyrust::clone!(q);
                    pyrust::vec::push!(raw, q[0]);
                    let mut exp: Vec<Position> = pyrust::vec::new!();
                    for p in q {
                        pyrust::vec::push!(exp, expand_outward(*p, centroid, expansion, w, h));
                    }
                    pyrust::vec::push!(exp, expand_outward(q[0], centroid, expansion, w, h));
                    vis(
                        &format!("patrol_cycle_{i}"),
                        &Dump::Path {
                            points: raw,
                            colour: Colour::new(255, 200, 80, 200),
                        },
                    );
                    vis(
                        &format!("patrol_cycle_{i}_expanded"),
                        &Dump::Path {
                            points: exp,
                            colour: Colour::new(120, 220, 255, 200),
                        },
                    );
                }
            }
            vis_scalar_int(
                "n_patrol_clusters",
                pyrust::len!(builder.patrol_clusters) as i64,
            );
            vis_scalar_int(
                "econ_explore_radius_sq",
                i64::from(builder.econ_explore_radius_sq),
            );
            vis_scalar_int(
                "rounds_since_harvester_add",
                i64::from(builder.state.round - builder.last_harvester_add_round),
            );
            // Union locus across all clusters: tiles within
            // sqrt(econ_explore_radius_sq) of any cluster member. ECON /
            // PermEcon explore-target picking is filtered to this set;
            // ore picking is NOT (uses econ_radius_sq instead).
            if n_clusters > 0 {
                let r2 = builder.econ_explore_radius_sq;
                let mut locus: HashSet<Position> = pyrust::set::new!();
                for cluster in &builder.patrol_clusters {
                    for m in cluster {
                        for y in 0..h {
                            for x in 0..w {
                                let p = Position { x, y };
                                if p.distance_squared(*m) <= r2 {
                                    pyrust::set::add!(locus, p);
                                }
                            }
                        }
                    }
                }
                vis_tiles("econ_explore_locus", pyrust::copied!(pyrust::iter!(locus)));
            }
            // for y in 0..h {
            //     let base = (y as usize) * MAX_WIDTH;
            //     let row_base = (y * w) as usize;
            //     for x in 0..w {
            //         let seen = builder.last_seen[base + (x as usize)];
            //         last_seen_grid[row_base + (x as usize)] = seen as i16;
            //         patrol_age[row_base + (x as usize)] = (crnd - seen) as f32;
            //     }
            // }
            // vis(
            //     "patrol_age",
            //     &Dump::F32Grid {
            //         data: patrol_age,
            //         palette: p_patrol(),
            //     },
            // );
            // vis(
            //     "last_seen",
            //     &Dump::I16Grid {
            //         data: last_seen_grid,
            //         palette: p_dist(),
            //     },
            // );
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
        });
    });
}
