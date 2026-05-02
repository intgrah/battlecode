//! Walk toward unexplored tiles to grow the bot's known map. Gated on
//! `ti > EXPLORE_MIN_TI`: exploring lays roads, so a starving bot would
//! strand titanium it can't recoup. Delegates the actual movement to
//! `builder::explore`.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::explore::explore as run_explore;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

#[pyrust::inline]
const EXPLORE_MIN_TI: i32 = 100;

pub fn explore(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if self_.ti <= EXPLORE_MIN_TI {
        return Some(TaskRejected::from_string(format!(
            "ti={} <= {}; exploring would burn roads we can't recoup",
            self_.ti, EXPLORE_MIN_TI
        )));
    }
    run_explore(self_, ct);
    None
}
