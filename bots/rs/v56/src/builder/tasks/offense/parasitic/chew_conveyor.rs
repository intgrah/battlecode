//! Fallback offense: with no vulnerable harvester and no cached target,
//! pick an enemy conveyor/splitter/bridge tile (via `pick_conveyor_target` —
//! prefers near-enemy-core, then visible-flow tiles, with spacing from our
//! other attackers) and either fire on it (if standing on it) or walk toward
//! it.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::helpers::{make_move, try_attack};
use crate::builder::tasks::offense::helpers::{
    pick_conveyor_target, should_attack, vulnerable_harvesters,
};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn chew_conveyor(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !pyrust::vec::is_empty!(vulnerable_harvesters(self_)) {
        return Some(TaskRejected::new(
            "a vulnerable harvester is in vision — handle that first",
        ));
    }
    if pyrust::is_some!(self_.offense_target) {
        return Some(TaskRejected::new(
            "offense_target is set — walk_to_cached_target handles it",
        ));
    }

    let enemy_core = self_.en_core_guess;
    let my_pos = self_.my_pos;
    let conveyor_target = pick_conveyor_target(self_, ct, enemy_core, my_pos);
    let Some(conveyor_target) = conveyor_target else {
        return Some(TaskRejected::new("pick_conveyor_target returned None"));
    };

    if my_pos == conveyor_target {
        if should_attack(self_, conveyor_target) {
            try_attack(ct, my_pos);
        }
    } else {
        make_move(self_, ct, conveyor_target);
    }
    None
}
