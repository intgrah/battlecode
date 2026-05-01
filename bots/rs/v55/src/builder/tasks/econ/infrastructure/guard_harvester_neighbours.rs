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
use crate::util::debug::debug as log;
use crate::util::directions::DIR4;
use crate::util::visualiser::auto_wrap_position;

pub fn guard_harvester_neighbours(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let mut targets: Vec<Position> = pyrust::vec::new!();
    for &pos in &self_.nearby_tiles {
        if self_.kind_at(pos) == Some(EntityType::Harvester)
            && self_.team_at(pos) == Some(self_.my_team)
            && self_.get_env(pos) == Some(Environment::OreTitanium)
        {
            pyrust::vec::push!(targets, pos);
        }
    }
    let my_pos = self_.my_pos;
    for tgt_opt in [self_.ore_target, self_.ax_ore_target] {
        if let Some(tgt) = tgt_opt
            && my_pos == tgt
            && !pyrust::vec::contains!(targets, &tgt)
        {
            pyrust::vec::push!(targets, tgt);
        }
    }

    if pyrust::vec::is_empty!(targets) {
        return Some(TaskRejected::new(
            "nothing to guard around any visible harvester / claim",
        ));
    }

    let near: HashSet<Position> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(self_.nearby_tiles)));
    let affords_road = can_afford(self_, EntityType::Road);
    let affords_guard = can_afford(self_, EntityType::Conveyor);

    let mut no_guard: HashSet<Position> = pyrust::set::new!();
    for &target in &targets {
        for p in harvester_io_cardinals(self_, target) {
            pyrust::set::add!(no_guard, p);
        }
    }

    for target in &targets {
        let target = *target;
        let feed = harvester_feed_cardinal(self_, target);
        let Some(feed) = feed else {
            continue;
        };

        if affords_road
            && pyrust::vec::contains!(near, &feed)
            && self_.get_cost(feed) > 1
            && pyrust::unwrap!(ct.can_build_road(feed))
        {
            let mut args = Map::new();
            pyrust::dict::insert!(args, pyrust::to_string!("feed"), auto_wrap_position(feed));
            log(
                "guard_harvester_neighbours: ROAD on feed {feed} (prep step-off)",
                args,
            );
            pyrust::unwrap!(ct.build_road(feed));
            return None;
        }

        if !affords_guard {
            continue;
        }
        for d in DIR4 {
            let pos = target.add(d);
            if !pyrust::vec::contains!(near, &pos) {
                continue;
            }
            if pyrust::vec::contains!(no_guard, &pos) {
                continue;
            }
            if !needs_harvester_guard(self_, pos, target, &no_guard) {
                continue;
            }
            if place_harvester_guard(self_, ct, pos, target) {
                return None;
            }
        }
    }
    Some(TaskRejected::new(
        "nothing to guard around any visible harvester / claim",
    ))
}
