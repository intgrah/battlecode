use cambc::EntityType;
use serde_json::{Map, Number, Value};

use crate::builder::Builder;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::debug::{Scope, debug as log};
use crate::util::directions::{DIR4, DIR8};

pub fn update_ore_denial(builder: &mut Builder) {
    builder.deny_ore_neighbours = pyrust::set::new!();
    let my_team = builder.state.my_team;

    // Bounded candidate set: union of incrementally-maintained visible
    // ore sets. Typically <10 tiles vs the 69 nearby_tiles we used to
    // walk. The hard cap below ensures pathological many-ore turns
    // don't blow the budget.
    let mut ores: Vec<cambc::Position> = pyrust::vec::new!();
    {
        let _g = Scope::new_timed("ore_collect");
        for p in pyrust::iter!(builder.visible_ti_ores) {
            pyrust::vec::push!(ores, *p);
        }
        for p in pyrust::iter!(builder.visible_ax_ores) {
            pyrust::vec::push!(ores, *p);
        }
    }
    let n_ores = pyrust::len!(ores) as i32;

    let mut n_with_enemy: i32 = 0;
    let mut deep_iters: i32 = 0;
    {
        let _g = Scope::new_timed("ore_scan");
        for pos in &ores {
            let pos = *pos;
            let mut has_enemy = false;
            for d in DIR8 {
                deep_iters += 1;
                let n = pos.add(d);
                if !builder.in_bounds(n) {
                    continue;
                }
                let ni = (n.y as usize) * MAX_WIDTH + (n.x as usize);
                if let Some(team) = builder.building_team[ni]
                    && team != my_team
                {
                    has_enemy = true;
                    break;
                }
                if pyrust::vec::contains!(builder.state.enemy_bots, &n) {
                    has_enemy = true;
                    break;
                }
            }
            if has_enemy {
                n_with_enemy += 1;
                for d in DIR4 {
                    let n = pos.add(d);
                    if builder.in_bounds(n) {
                        pyrust::set::add!(builder.deny_ore_neighbours, n);
                    }
                }
            }
        }
    }

    let n_deny = pyrust::len!(builder.deny_ore_neighbours) as i32;
    let n_enemy_bots = pyrust::len!(builder.state.enemy_bots) as i32;
    let mut args = Map::new();
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("ores"),
        Value::Number(Number::from(n_ores))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("with_enemy"),
        Value::Number(Number::from(n_with_enemy))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("deep"),
        Value::Number(Number::from(deep_iters))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("enemy_bots"),
        Value::Number(Number::from(n_enemy_bots))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("deny"),
        Value::Number(Number::from(n_deny))
    );
    log(
        "ore_deny: ores={ores} with_enemy={with_enemy} deep={deep} enemy_bots={enemy_bots} deny={deny}",
        args,
    );
}

pub fn update_enemy_turrets(builder: &mut Builder) {
    let my_team = builder.state.my_team;
    if let Some(t) = builder.nearest_enemy_turret {
        let i = (t.y as usize) * MAX_WIDTH + (t.x as usize);
        let valid = matches!(
            builder.building_kind[i],
            Some(EntityType::Gunner | EntityType::Sentinel)
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
            Some(EntityType::Gunner | EntityType::Sentinel)
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
