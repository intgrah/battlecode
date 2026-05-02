use cambc::{EntityType, Environment, Position};

use crate::builder::Builder;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::directions::{DIR4_DELTA, DIR8_DELTA};
use crate::util::posint::{dist_sq, idx_of, pos_of};

pub fn update_ore_denial(builder: &mut Builder) {
    let my_team = builder.state.my_team;
    let w = builder.state.width;
    let h = builder.state.height;
    // Hoist field references so the Python translation does one attribute
    // lookup per call instead of one per inner-loop iteration.
    let bteam = &builder.building_team;
    let enemy_bots = &builder.state.enemy_bots;
    let mut deny_set: std::collections::HashSet<i32> = pyrust::set::new!();
    // Iterate the typed ore sub-lists maintained by update_vision instead
    // of scanning all 60 nearby_tiles. ~5-15 ore tiles vs 60 — 4-12× fewer
    // outer iterations and we drop the per-tile env lookup entirely.
    // Lists hold `PosInt` (already-computed flat index).
    let mut ore_tiles: Vec<i32> = pyrust::clone!(builder.visible_ti_ore);
    pyrust::vec::extend!(
        ore_tiles,
        pyrust::copied!(pyrust::iter!(builder.visible_ax_ore))
    );
    for &pi in &ore_tiles {
        let pos = pos_of(pi);
        let px = pos.x;
        let py = pos.y;
        let mut has_enemy = false;
        for &(dx, dy) in &DIR8_DELTA {
            let nx = px + dx;
            let ny = py + dy;
            if nx < 0 || nx >= w || ny < 0 || ny >= h {
                continue;
            }
            let n = Position { x: nx, y: ny };
            let ni = idx_of(n) as usize;
            if let Some(team) = bteam[ni]
                && team != my_team
            {
                has_enemy = true;
                break;
            }
            if pyrust::set::contains!(enemy_bots, &n) {
                has_enemy = true;
                break;
            }
        }
        if has_enemy {
            for &(dx, dy) in &DIR4_DELTA {
                let nx = px + dx;
                let ny = py + dy;
                if nx >= 0 && nx < w && ny >= 0 && ny < h {
                    pyrust::set::add!(deny_set, ny * 100 + nx);
                }
            }
        }
    }
    builder.deny_ore_neighbours = deny_set;
}

pub fn update_enemy_turrets(builder: &mut Builder) {
    let my_team = builder.state.my_team;
    let bk = &builder.building_kind;
    let bt = &builder.building_team;
    if let Some(t) = builder.nearest_enemy_turret {
        let i = idx_of(t) as usize;
        let kind = bk[i];
        let team = bt[i];
        let valid = matches!(kind, Some(EntityType::Gunner | EntityType::Sentinel))
            && team != Some(my_team)
            && pyrust::is_some!(team);
        if !valid {
            builder.nearest_enemy_turret = None;
        }
    }

    let mut min_dist = INF;
    let mut nearest: Option<Position> = builder.nearest_enemy_turret;
    let my_p = idx_of(builder.state.my_pos);
    for pos in &builder.state.nearby_tiles {
        let pi = idx_of(*pos);
        let i = pi as usize;
        let kind = bk[i];
        let team = bt[i];
        let is_enemy_turret = matches!(kind, Some(EntityType::Gunner | EntityType::Sentinel))
            && team != Some(my_team)
            && pyrust::is_some!(team);
        if is_enemy_turret {
            let dist = dist_sq(my_p, pi);
            if dist < min_dist {
                min_dist = dist;
                nearest = Some(*pos);
            }
        }
    }
    builder.nearest_enemy_turret = nearest;
}
