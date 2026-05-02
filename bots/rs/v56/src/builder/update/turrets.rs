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

    let mut min_dist = INF;
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    for pos in &nearby {
        let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
        let is_enemy_turret = matches!(
            builder.building_kind[i],
            Some(EntityType::Gunner | EntityType::Sentinel | EntityType::Launcher)
        ) && builder.building_team[i] != Some(my_team)
            && pyrust::is_some!(builder.building_team[i]);
        if is_enemy_turret {
            let dist = builder.state.my_pos.distance_squared(*pos);
            if dist < min_dist {
                min_dist = dist;
                builder.nearest_enemy_turret = Some(*pos);
            }
        }
    }
}
