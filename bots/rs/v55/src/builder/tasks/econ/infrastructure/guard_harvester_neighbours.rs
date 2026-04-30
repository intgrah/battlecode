//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/guard_harvester_neighbours.py`.
//!
//! Guard work around our Ti harvesters / claimed-but-unbuilt ore tiles.

use std::collections::HashSet;

use cambc::{Controller, ControllerApi, EntityType, Environment, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::harvest::{needs_harvester_guard, place_harvester_guard};
use crate::builder::helpers::{can_afford, harvester_feed_cardinal, harvester_io_cardinals};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::building::Building;
use crate::util::debug::debug as log;
use crate::util::directions::DIR4;
use crate::util::visualiser::auto_wrap_position;

pub fn guard_harvester_neighbours(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let mut targets: Vec<Position> = Vec::new();
    for &pos in &self_.nearby_tiles {
        let b = self_.get_building(pos);
        if let Some(Building::Harvester { team }) = b
            && team == self_.my_team
            && self_.get_env(pos) == Some(Environment::OreTitanium)
        {
            targets.push(pos);
        }
    }
    let my_pos = self_.my_pos;
    for tgt_opt in [self_.ore_target, self_.ax_ore_target] {
        if let Some(tgt) = tgt_opt
            && my_pos == tgt
            && !targets.contains(&tgt)
        {
            targets.push(tgt);
        }
    }

    if targets.is_empty() {
        return Err(TaskRejected::new(
            "nothing to guard around any visible harvester / claim",
        ));
    }

    let near: HashSet<Position> = self_.nearby_tiles.iter().copied().collect();
    let affords_road = can_afford(self_, EntityType::Road);
    let affords_guard = can_afford(self_, EntityType::Conveyor);

    let mut no_guard: HashSet<Position> = HashSet::new();
    for &target in &targets {
        for p in harvester_io_cardinals(self_, target) {
            no_guard.insert(p);
        }
    }

    for target in &targets {
        let target = *target;
        let feed = harvester_feed_cardinal(self_, target);
        let Some(feed) = feed else {
            continue;
        };

        if affords_road
            && near.contains(&feed)
            && self_.get_cost(feed) > 1
            && ct.can_build_road(feed).unwrap()
        {
            let mut args = Map::new();
            args.insert("feed".to_string(), auto_wrap_position(feed));
            log(
                "guard_harvester_neighbours: ROAD on feed {feed} (prep step-off)",
                args,
            );
            ct.build_road(feed).unwrap();
            return Ok(());
        }

        if !affords_guard {
            continue;
        }
        for d in DIR4 {
            let pos = target.add(d);
            if !near.contains(&pos) {
                continue;
            }
            if no_guard.contains(&pos) {
                continue;
            }
            if !needs_harvester_guard(self_, pos, target, &no_guard) {
                continue;
            }
            if place_harvester_guard(self_, ct, pos, target) {
                return Ok(());
            }
        }
    }
    Err(TaskRejected::new(
        "nothing to guard around any visible harvester / claim",
    ))
}
