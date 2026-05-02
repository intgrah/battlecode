use cambc::EntityType;

use crate::builder::Builder;
use crate::util::constants::{INF, MAX_WIDTH};

pub fn update_enemy_turrets(builder: &mut Builder) {
    let my_team = builder.state.my_team;
    if let Some(t) = builder.nearest_enemy_turret {
        let i = (t.y as usize) * MAX_WIDTH + (t.x as usize);
        let valid = matches!(
            builder.building_kind[i],
            Some(EntityType::Gunner | EntityType::Sentinel | EntityType::Launcher)
        ) && builder.building_team[i] != Some(my_team);
        if !valid {
            builder.nearest_enemy_turret = None;
        }
    }

    builder.enemy_turrets = pyrust::vec::new!();
    let mut min_dist = INF;
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    for pos in &nearby {
        let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
        let kind = builder.building_kind[i];
        let team = builder.building_team[i];
        let is_enemy = pyrust::is_some!(team) && team != Some(my_team);
        if !is_enemy {
            continue;
        }
        // Full enemy-turret list: Gunner, Sentinel, Launcher, Breach.
        if matches!(
            kind,
            Some(
                EntityType::Gunner
                    | EntityType::Sentinel
                    | EntityType::Launcher
                    | EntityType::Breach
            )
        ) {
            pyrust::vec::push!(builder.enemy_turrets, *pos);
        }
        // `nearest_enemy_turret` covers Gunner / Sentinel / Launcher
        // (post-merge with adgato's widening). Sentinels can shoot
        // launchers, so launcher counts as a sentinel-fallback target.
        if matches!(
            kind,
            Some(EntityType::Gunner | EntityType::Sentinel | EntityType::Launcher)
        ) {
            let dist = builder.state.my_pos.distance_squared(*pos);
            if dist < min_dist {
                min_dist = dist;
                builder.nearest_enemy_turret = Some(*pos);
            }
        }
    }
}
