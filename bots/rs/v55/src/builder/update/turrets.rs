use std::collections::HashSet;

use cambc::Environment;

use crate::builder::Builder;
use crate::building::Building;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::directions::{DIR4, DIR8};

pub fn update_ore_denial(builder: &mut Builder) {
    builder.deny_ore_neighbours = HashSet::new();
    let nearby = builder.state.nearby_tiles.clone();
    for pos in &nearby {
        let env = builder.env[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)];
        if env != Some(Environment::OreTitanium) && env != Some(Environment::OreAxionite) {
            continue;
        }
        let mut has_enemy = false;
        for d in DIR8 {
            let n = pos.add(d);
            if !builder.in_bounds(n) {
                continue;
            }
            let nb = builder.buildings[(n.y as usize) * MAX_WIDTH + (n.x as usize)];
            if let Some(b) = nb
                && b.team() != builder.state.my_team
            {
                has_enemy = true;
                break;
            }
            if builder.state.enemy_bots.contains(&n) {
                has_enemy = true;
                break;
            }
        }
        if has_enemy {
            for d in DIR4 {
                let n = pos.add(d);
                if builder.in_bounds(n) {
                    builder.deny_ore_neighbours.insert(n);
                }
            }
        }
    }
}

pub fn update_enemy_turrets(builder: &mut Builder) {
    if let Some(t) = builder.nearest_enemy_turret {
        let i = (t.y as usize) * MAX_WIDTH + (t.x as usize);
        let valid = matches!(
            builder.buildings[i],
            Some(Building::Gunner { team, .. } | Building::Sentinel { team, .. })
                if team != builder.state.my_team
        );
        if !valid {
            builder.nearest_enemy_turret = None;
        }
    }

    let mut min_dist = INF;
    let nearby = builder.state.nearby_tiles.clone();
    for pos in &nearby {
        let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
        let is_enemy_turret = matches!(
            builder.buildings[i],
            Some(Building::Gunner { team, .. } | Building::Sentinel { team, .. })
                if team != builder.state.my_team
        );
        if is_enemy_turret {
            let dist = builder.state.my_pos.distance_squared(*pos);
            if dist < min_dist {
                min_dist = dist;
                builder.nearest_enemy_turret = Some(*pos);
            }
        }
    }
}
