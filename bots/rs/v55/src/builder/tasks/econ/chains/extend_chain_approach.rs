//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/chains/extend_chain_approach.py`.
//!
//! Walk toward `dangling_output` and lay a conveyor segment along the
//! A* path to its sink (Ti -> ti_sink, Ax -> ax_sink). No range gate — the
//! builder will travel as far as needed. Fires only when the in-range
//! variant rejects (dangling end out of vision). The cached
//! `dangling_output` is refreshed every turn by `update_dangling` (no
//! stickiness).

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::chain_routing::extend_chain;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn extend_chain_approach(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(dangling) = self_.dangling_output else {
        return Err(TaskRejected::new("no dangling output"));
    };
    extend_chain(self_, ct, dangling)
}
