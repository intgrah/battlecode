//! Step off the claimed ore tile and place a harvester in the same
//! turn. Lowest-priority of the three ore-claim phases — fires only after
//! `claim_ore` is satisfied (we stand on the ore) and `guard_harvester_neighbours`
//! has nothing more to add to the ring.

use cambc::{Controller, EntityType, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::harvest::{clear_barriered_feed, step_off_and_build_harvester};
use crate::builder::helpers::{can_afford, harvester_feed_cardinal, ore_available, try_attack};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::debug::debug as log;
use crate::util::visualiser::auto_wrap_position;

const fn resolve_target(self_: &Builder) -> Option<Position> {
    if let Some(t) = self_.ore_target {
        return Some(t);
    }
    if let Some(t) = self_.ax_ore_target {
        return Some(t);
    }
    None
}

pub fn build_harvester(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(target) = resolve_target(self_) else {
        return Some(TaskRejected::new(
            "no ore_target / ax_ore_target to harvest",
        ));
    };
    if self_.my_pos != target {
        return Some(TaskRejected::from_string(format!(
            "not standing on ore {target:?}"
        )));
    }
    if !ore_available(self_, target) {
        self_.ore_target = None;
        return Some(TaskRejected::new(
            "no ore_target / ax_ore_target to harvest",
        ));
    }
    // If there's an enemy building on the ore tile, fire at it regardless
    // of harvester affordability — destroying it unblocks placement.
    if let Some((_, team)) = self_.get_building(target)
        && team != self_.my_team
    {
        let mut args = Map::new();
        pyrust::dict::insert!(args, pyrust::to_string!("target"), auto_wrap_position(target));
        log("build_harvester: firing on enemy building at {target}", args);
        try_attack(ct, target);
        return None;
    }
    if !can_afford(self_, EntityType::Harvester) {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("target"),
            auto_wrap_position(target)
        );
        log(
            "build_harvester: waiting on Ti for HARVESTER on {target}",
            args,
        );
        return None;
    }
    if pyrust::is_none!(harvester_feed_cardinal(self_, target)) {
        if !clear_barriered_feed(self_, ct, target) {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target)
            );
            log(
                "build_harvester: no viable feed cardinal for {target}; waiting",
                args,
            );
        }
        return None;
    }
    if !step_off_and_build_harvester(self_, ct, target) {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("target"),
            auto_wrap_position(target)
        );
        log(
            "build_harvester: could not step off {target} this turn; waiting",
            args,
        );
    }
    None
}
