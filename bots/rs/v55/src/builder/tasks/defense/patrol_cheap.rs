//! Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/patrol_cheap.py`.
//!
//! Walk a defensive route around our economy, but only when we can't
//! afford a harvester (otherwise the Ti is better spent on another harvester
//! build). Used by DEFENSE role early-game when funds are tight; later the
//! late-patrol variant takes over.

use cambc::{Controller, EntityType};

use crate::builder::Builder;
use crate::builder::helpers::can_afford;
use crate::builder::patrol::run_patrol;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn patrol_cheap(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if can_afford(self_, EntityType::Harvester) {
        return Some(TaskRejected::new(
            "can afford a harvester, should build instead of patrol",
        ));
    }
    if !run_patrol(self_, ct) {
        return Some(TaskRejected::new("run_patrol produced no action"));
    }
    None
}
