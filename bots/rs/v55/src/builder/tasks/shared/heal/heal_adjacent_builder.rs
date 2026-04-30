//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/heal_adjacent_builder.py`.
//!
//! Heal a damaged friendly builder bot within action range. Skips
//! bots standing on a damaged enemy building — those bots are mid-kill
//! and would lose progress if we patched them up. Bails out under the
//! "fight to death" gate (low-HP self on enemy tile).

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;
use crate::builder::helpers::try_heal;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::builder::tasks::shared::heal::_helpers::{fight_to_death, has_wounded_enemy};

pub fn heal_adjacent_builder(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if fight_to_death(self_, ct) {
        return Err(TaskRejected::new(
            "low HP on enemy tile — fight to death, no heal",
        ));
    }
    let adjacent_builders = ct.get_nearby_units(Some(2)).unwrap();
    for eid in adjacent_builders {
        if ct.get_hp(Some(eid)).unwrap() <= ct.get_max_hp(Some(eid)).unwrap() - 4
            && ct.get_team(Some(eid)).unwrap() == self_.my_team
        {
            let position = ct.get_position(Some(eid)).unwrap();
            if has_wounded_enemy(self_, position) {
                continue;
            }
            if try_heal(self_, ct, position, false) {
                return Ok(());
            }
        }
    }
    Err(TaskRejected::new("no damaged friendly bot in heal range"))
}
