//! Defensive patrol task. Just dispatches to `run_patrol`. Priority
//! and exploration-vs-tightness are controlled externally — by the
//! alert-gated policy groups in `defense/mod.rs` and by the alert
//! field that `run_patrol` reads when computing the expansion radius.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::patrol::run_patrol;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn patrol(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !run_patrol(self_, ct) {
        return Some(TaskRejected::new("run_patrol produced no action"));
    }
    None
}
