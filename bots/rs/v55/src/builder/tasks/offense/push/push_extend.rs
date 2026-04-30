//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/push_extend.py`.
//!
//! Extend `dangling_output` toward the enemy core (instead of `ti_sink`
//! or `my_core`). Used after a forward harvester is planted, growing the
//! offensive chain toward enemy lines. Requires symmetry to be resolved so
//! `en_core_guess` returns a known position.

use cambc::{Controller, ResourceType};

use crate::builder::Builder;
use crate::builder::chain_routing::{extend_step, resource_at};
use crate::builder::helpers::on_enemy_side;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn push_extend(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if self_.symmetry().is_none() {
        return Err(TaskRejected::new("symmetry unresolved; en_core unknown"));
    }
    let Some(start) = self_.dangling_output else {
        return Err(TaskRejected::new("no dangling output"));
    };
    if !on_enemy_side(self_, start) {
        return Err(TaskRejected::from_string(format!(
            "dangling {:?} is on our side of the bisector",
            start
        )));
    }
    let resource = resource_at(self_, start);
    if resource != Some(ResourceType::Titanium) {
        return Err(TaskRejected::from_string(format!(
            "dangling {:?} is {:?}, push_extend is Ti-only",
            start, resource
        )));
    }
    let target = self_.en_core_guess;
    extend_step(self_, ct, start, target, ResourceType::Titanium)
}
