//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/wander.py`.
//!
//! Walk-away-from-core fallback for ECON / DEFENSE roles. Tries each
//! of the 8 directions in order of decreasing Chebyshev distance from
//! our core, walking only on pre-existing walkable tiles — no road
//! paving (no Ti spend). Rejects if no direction produces a legal move.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::helpers::try_move_dir;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR8;
use crate::util::metrics::chebyshev;

pub fn wander(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let my_pos = self_.my_pos;
    let my_core = self_.my_core;
    let mut dirs = pyrust::to_vec!(DIR8);
    pyrust::sort_by_key!(dirs, |&d| -chebyshev(my_pos.add(d), my_core));
    for d in dirs {
        if try_move_dir(ct, d) {
            return None;
        }
    }
    Some(TaskRejected::new(
        "no walkable direction available without paving",
    ))
}
