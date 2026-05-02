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
        return Some(TaskRejected::new("builder is not in opportunistic mode"));
    }
    let r = self_.rng.random();
    if r >= 0.2 {
        return Some(TaskRejected::new("random gate (p=0.2) declined"));
    }
    if self_.round <= 100 {
        return Some(TaskRejected::from_string(format!(
            "round {} <= 100",
            self_.round
        )));
    }
    if !pyrust::unwrap!(ct.can_fire(self_.my_pos)) {
        return Some(TaskRejected::new("ct.can_fire(my_pos) is False"));
    }
    let bid = pyrust::unwrap!(ct.get_tile_building_id(self_.my_pos));
    if pyrust::unwrap!(ct.get_team(bid)) == self_.my_team {
        return Some(TaskRejected::new(
            "tile under builder holds a friendly building",
        ));
    }
    pyrust::unwrap!(ct.fire(self_.my_pos));
    None
}
