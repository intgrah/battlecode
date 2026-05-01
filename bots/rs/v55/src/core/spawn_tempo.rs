//! Translation of `bots/intgrah/v54.7.9/core/spawn_tempo.py`.
//!
//! Spawn tempo: a per-game scalar derived from map features visible to the
//! Core at `post_init` time. Higher tempo -> spawn more aggressively; lower
//! tempo -> spawn slower (denser walls, eccentric core, etc.).
//!
//! Constants were fitted from hand-rated maps (1-5 scale, "how many builders
//! should this map spawn") and folded through the affine transform
//! `tempo = 1.0 + (rating - 3.0) * 0.15`, so the model maps features
//! directly to a tempo multiplier centred on 1.0.

use cambc::{Controller, ControllerApi, Environment, Position};

const BIAS: f64 = 1.6306;
const W_ECCENTRICITY: f64 = -0.5978;
const W_EDGE_DIST: f64 = -0.0143;
const W_CARDINAL_EXITS: f64 = -0.0114;
const W_INNER_WALL_DENSITY: f64 = -0.2698;
const W_OUTER_WALL_DENSITY: f64 = -0.2340;
const W_NEAREST_TI_D2: f64 = -0.0109;
const W_NEAREST_WALL_D2: f64 = -0.0015;

const CORE_VISION_R2: i32 = 36;
const INNER_R2: i32 = 8;

/// Compute the spawn-tempo multiplier directly from post_init-visible map
/// features. ~1.0 for an average map; ~0.7 for low-spawn maps (eccentric
/// core, dense walls, far ore); ~1.3 for high-spawn maps (central, open,
/// ore-rich nearby).
#[must_use]
pub fn compute_spawn_tempo(width: i32, height: i32, ct: &mut Controller<'_>) -> f64 {
    let pos = ct.get_position(None).unwrap();
    let cx = pos.x;
    let cy = pos.y;
    let w = width;
    let h = height;

    let centre_dist = (cx - w / 2).abs().max((cy - h / 2).abs());
    let eccentricity = pyrust::float!(centre_dist) / pyrust::float!(w.max(h).max(1));
    let edge_dist = cx.min(cy).min(w - 1 - cx).min(h - 1 - cy);

    let mut cardinal_exits: i32 = 0;
    for (dx, dy) in [(-2, 0), (2, 0), (0, -2), (0, 2)] {
        let x = cx + dx;
        let y = cy + dy;
        if x >= 0 && x < w && y >= 0 && y < h {
            let env = ct.get_tile_env(Position { x, y }).unwrap();
            if env != Environment::Wall {
                cardinal_exits += 1;
            }
        }
    }

    let mut inner_walls: i32 = 0;
    let mut inner_total: i32 = 0;
    let mut outer_walls: i32 = 0;
    let mut outer_total: i32 = 0;
    let mut nearest_ti_d2: i32 = CORE_VISION_R2 + 1;
    let mut nearest_wall_d2: i32 = CORE_VISION_R2 + 1;

    for dy in -6..=6 {
        for dx in -6..=6 {
            let d2 = dx * dx + dy * dy;
            if d2 > CORE_VISION_R2 {
                continue;
            }
            let x = cx + dx;
            let y = cy + dy;
            if !(x >= 0 && x < w && y >= 0 && y < h) {
                continue;
            }
            let env = ct.get_tile_env(Position { x, y }).unwrap();
            let is_wall = env == Environment::Wall;
            if d2 <= INNER_R2 {
                inner_total += 1;
                if is_wall {
                    inner_walls += 1;
                }
            } else {
                outer_total += 1;
                if is_wall {
                    outer_walls += 1;
                }
            }
            if is_wall && d2 < nearest_wall_d2 {
                nearest_wall_d2 = d2;
            }
            if env == Environment::OreTitanium && d2 < nearest_ti_d2 {
                nearest_ti_d2 = d2;
            }
        }
    }

    let inner_wall_density = pyrust::float!(inner_walls) / pyrust::float!(inner_total.max(1));
    let outer_wall_density = pyrust::float!(outer_walls) / pyrust::float!(outer_total.max(1));

    BIAS + W_ECCENTRICITY * eccentricity
        + W_EDGE_DIST * pyrust::float!(edge_dist)
        + W_CARDINAL_EXITS * pyrust::float!(cardinal_exits)
        + W_INNER_WALL_DENSITY * inner_wall_density
        + W_OUTER_WALL_DENSITY * outer_wall_density
        + W_NEAREST_TI_D2 * pyrust::float!(nearest_ti_d2)
        + W_NEAREST_WALL_D2 * pyrust::float!(nearest_wall_d2)
}
