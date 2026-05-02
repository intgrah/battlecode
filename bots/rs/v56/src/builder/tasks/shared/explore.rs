//! Walk toward unexplored tiles to grow the bot's known map. Gated on
//! `ti > EXPLORE_MIN_TI`: exploring lays roads, so a starving bot would
//! strand titanium it can't recoup. Delegates the actual movement to
//! `builder::explore`.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::explore::explore as run_explore;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn explore(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if run_explore(self_, ct) {
        return None;
    }
    Some(TaskRejected::from_string(format!(
        "didn't move during explore"
    )))
}
