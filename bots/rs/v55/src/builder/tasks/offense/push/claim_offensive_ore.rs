//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/claim_offensive_ore.py`.
//!
//! Walk onto `offensive_ore_target` (enemy-side ore picked by the
//! inverse-bisector gate) to claim it. Mirrors `claim_ore` but uses the
//! offense-specific target.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::harvest::walk_to_ore_claim;
use crate::builder::helpers::ore_available;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn claim_offensive_ore(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(target) = self_.offensive_ore_target else {
        return Some(TaskRejected::new("offensive_ore_target is None"));
    };
    if self_.my_pos == target {
        return Some(TaskRejected::from_string(format!(
            "already on offensive ore {target:?}"
        )));
    }
    if !ore_available(self_, target) {
        return Some(TaskRejected::from_string(format!(
            "offensive ore {target:?} unavailable"
        )));
    }
    if !walk_to_ore_claim(self_, ct, target) {
        return Some(TaskRejected::from_string(format!(
            "no progress toward {target:?}"
        )));
    }
    None
}
