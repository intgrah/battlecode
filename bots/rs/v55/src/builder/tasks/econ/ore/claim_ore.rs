//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/ore/claim_ore.py`.
//!
//! Walk onto an unharvested ore tile to claim it. Highest-priority of
//! the three ore-claim phases. Single responsibility: navigate (with
//! contest-clearing) onto `ore_target` or `ax_ore_target`. No conveyor
//! placement, no harvester placement.

use cambc::{Controller, Position};

use crate::builder::Builder;
use crate::builder::harvest::walk_to_ore_claim;
use crate::builder::helpers::ore_available;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

fn resolve_target(self_: &Builder) -> Option<Position> {
    if let Some(t) = self_.ore_target {
        return Some(t);
    }
    if let Some(t) = self_.ax_ore_target
        && self_.ax_sink.is_some()
    {
        return Some(t);
    }
    None
}

pub fn claim_ore(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(target) = resolve_target(self_) else {
        return Err(TaskRejected::new("no ore_target / ax_ore_target to claim"));
    };
    if self_.my_pos == target {
        return Err(TaskRejected::from_string(format!(
            "already standing on ore {:?}",
            target
        )));
    }
    if !ore_available(self_, target) {
        return Err(TaskRejected::from_string(format!(
            "ore {:?} no longer available",
            target
        )));
    }
    if !walk_to_ore_claim(self_, ct, target) {
        return Err(TaskRejected::from_string(format!(
            "could not progress toward ore {:?}",
            target
        )));
    }
    Ok(())
}
