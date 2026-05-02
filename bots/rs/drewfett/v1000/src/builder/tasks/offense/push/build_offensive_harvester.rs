//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/build_offensive_harvester.py`.
//!
//! Step off the claimed offensive ore and place a Ti harvester. Mirrors
//! `build_harvester` (and shares its anchor-when-waiting semantics).

use cambc::{Controller, EntityType};
use serde_json::Map;
use crate::config::DEBUG_LOG;

use crate::builder::Builder;
use crate::builder::harvest::{clear_barriered_feed, step_off_and_build_harvester};
use crate::builder::helpers::{can_afford, harvester_feed_cardinal, ore_available};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::debug::debug as log;
use crate::util::visualiser::auto_wrap_position;

pub fn build_offensive_harvester(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(target) = self_.offensive_ore_target else {
        return Some(TaskRejected::new("offensive_ore_target is None"));
    };
    if self_.my_pos != target {
        return Some(TaskRejected::from_string(format!(
            "not on offensive ore {target:?}"
        )));
    }
    if !ore_available(self_, target) {
        return Some(TaskRejected::new("offensive_ore_target is None"));
    }
    if !can_afford(self_, EntityType::Harvester) {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
            args,
            pyrust::to_string!("target"),
            auto_wrap_position(target)
            );
            log(
            "build_offensive_harvester: waiting on Ti for {target}",
            args,
            );
        }
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
                "build_offensive_harvester: no feed cardinal for {target}; waiting",
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
            "build_offensive_harvester: cannot step off {target}; waiting",
            args,
        );
    }
    None
}
