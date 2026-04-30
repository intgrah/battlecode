//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/opportunistic_attack.py`.
//!
//! Cheap, low-priority opportunistic fire used by ECON / DEFENSE roles.
//! A small fraction of builders (`self.opportunistic` set at init) randomly
//! fire (p=0.2) on the enemy building under their feet, but only after round
//! 100. Distinct from OFFENSE's structured attack cascade — this is just
//! "if standing on an enemy thing, occasionally hit it".

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn opportunistic_attack(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !self_.opportunistic {
        return Err(TaskRejected::new("builder is not in opportunistic mode"));
    }
    let r = (self_.rng.next_u64() as f64) / (u64::MAX as f64);
    if r >= 0.2 {
        return Err(TaskRejected::new("random gate (p=0.2) declined"));
    }
    if self_.round <= 100 {
        return Err(TaskRejected::from_string(format!(
            "round {} <= 100",
            self_.round
        )));
    }
    if !ct.can_fire(self_.my_pos).unwrap() {
        return Err(TaskRejected::new("ct.can_fire(my_pos) is False"));
    }
    let bid = ct.get_tile_building_id(self_.my_pos).unwrap();
    if ct.get_team(bid).unwrap() == self_.my_team {
        return Err(TaskRejected::new(
            "tile under builder holds a friendly building",
        ));
    }
    ct.fire(self_.my_pos).unwrap();
    Ok(())
}
