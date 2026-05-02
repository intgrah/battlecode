use cambc::{Controller, EntityType};

use crate::builder::Builder;
use crate::builder::helpers::can_afford;
use crate::builder::patrol::run_patrol;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

/// Defensive patrol: cluster-aware cyclic walk with alert-graded expansion.
/// Gated on "broke" — if we can afford a harvester, that Ti is better
/// spent building, so reject and let the next sibling task fire.
pub fn patrol(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if can_afford(self_, EntityType::Harvester) {
        return Some(TaskRejected::new(
            "can afford harvester, build instead of patrol",
        ));
    }
    if !run_patrol(self_, ct) {
        return Some(TaskRejected::new("run_patrol produced no action"));
    }
    None
}
