//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/chains/extend_chain_in_range.py`.
//!
//! Lay a conveyor segment from `dangling_output` toward its sink, only
//! when the dangling end is within builder vision. The cached
//! `dangling_output` is refreshed every turn by `update_dangling` (no
//! stickiness), and the proximity gate inside the picker ensures only the
//! rightful claimant builder considers a given end.

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;
use crate::builder::chain_routing::extend_chain;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn extend_chain_in_range(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(dangling) = self_.dangling_output else {
        return Err(TaskRejected::new("no dangling output"));
    };
    if !ct.is_in_vision(dangling).unwrap() {
        return Err(TaskRejected::from_string(format!(
            "dangling {:?} not in vision",
            dangling
        )));
    }
    extend_chain(self_, ct, dangling)
}
