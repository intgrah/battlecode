//! Soft cost-grid penalty for tiles threatened by enemy turrets and
//! launchers. Bumps `cost_grid[i]` by `THREAT_PENALTY` so `dp_step`'s
//! weighted tiebreak detours around them when an alternate tile of equal
//! plan-progress exists. Reverted-and-reapplied each turn so the bump
//! only persists while the threat set still contains the tile.

use crate::builder::Builder;
use crate::builder::update::vision::_update_cost;
use crate::util::constants::{INF, MAX_WIDTH};

/// Additive penalty applied to threatened tiles. Sized so `dp_step`
/// prefers a detour of up to ~16 extra `ROAD_COST` hops (50 / 3) over
/// walking through a turret ray.
pub const THREAT_PENALTY: i32 = 50;

pub fn apply_threat_overlay(builder: &mut Builder) {
    let bumped_indices: Vec<usize> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(builder._threat_bumped)));
    for i in bumped_indices {
        let env = builder.env[i];
        let kind = builder.building_kind[i];
        let team = builder.building_team[i];
        _update_cost(builder, i, env, kind, team);
    }
    builder._threat_bumped.clear();

    let enemy_tiles: Vec<_> = pyrust::collect!(pyrust::copied!(pyrust::iter!(
        builder.enemy_turret_ray_tiles
    )));
    for tile in enemy_tiles {
        let i = (tile.y as usize) * MAX_WIDTH + (tile.x as usize);
        if builder.cost_grid[i] != INF && !pyrust::vec::contains!(builder._threat_bumped, &i) {
            builder.cost_grid[i] += THREAT_PENALTY;
            pyrust::set::add!(builder._threat_bumped, i);
        }
    }
    let launcher_tiles: Vec<_> = pyrust::collect!(pyrust::copied!(pyrust::iter!(
        builder.adjacent_to_enemy_launcher
    )));
    for tile in launcher_tiles {
        let i = (tile.y as usize) * MAX_WIDTH + (tile.x as usize);
        if builder.cost_grid[i] != INF && !pyrust::vec::contains!(builder._threat_bumped, &i) {
            builder.cost_grid[i] += THREAT_PENALTY;
            pyrust::set::add!(builder._threat_bumped, i);
        }
    }
}
