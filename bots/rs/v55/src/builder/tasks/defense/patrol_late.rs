//! Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/patrol_late.py`.
//!
//! Late-game defensive patrol: only fires when at least one friendly
//! harvester is in vision (otherwise there's nothing to defend nearby).
//! Lower priority than `patrol_cheap` in the DEFENSE policy — the cheap
//! variant gates on "broke", this one gates on "have something to guard".

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::patrol::run_patrol;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn patrol_late(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if self_.adjacent_to_harvester.is_empty() {
        return Some(TaskRejected::new(
            "no friendly harvester-adjacent tile in view",
        ));
    }
    if !run_patrol(self_, ct) {
        return Some(TaskRejected::new("run_patrol produced no action"));
    }
    None
}
