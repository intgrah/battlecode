//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/heal_self.py`.
//!
//! Heal own tile. If standing on an enemy building, step off first
//! (otherwise the heal is wasted on the enemy structure too) — but only
//! when there's an unwounded escape direction. Bails out under the
//! "fight to death" gate (low-HP self on enemy tile).

use cambc::{Controller, ControllerApi, GameConstants};

use crate::builder::Builder;
use crate::builder::helpers::{move_random, try_heal};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::builder::tasks::shared::heal::_helpers::{fight_to_death, has_wounded_enemy};

pub fn heal_self(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if fight_to_death(self_, ct) {
        return Some(TaskRejected::new(
            "low HP on enemy tile — fight to death, no heal",
        ));
    }
    if pyrust::unwrap!(ct.get_hp(None))
        > pyrust::unwrap!(ct.get_max_hp(None)) - GameConstants::HEAL_AMOUNT
    {
        return Some(TaskRejected::new(
            "self HP within HEAL_AMOUNT of max — heal would waste Ti",
        ));
    }

    let my_pos = self_.my_pos;
    if !has_wounded_enemy(self_, my_pos) {
        try_heal(self_, ct, my_pos, false);
        move_random(self_, ct);
        return None;
    }

    let dir_neighbours_8 = pyrust::clone!(self_.dir_neighbours_8);
    for (d, n) in dir_neighbours_8 {
        if pyrust::unwrap!(ct.can_move(d)) && !has_wounded_enemy(self_, n) {
            pyrust::unwrap!(ct.move_(d));
            let cur = pyrust::unwrap!(ct.get_position(None));
            try_heal(self_, ct, cur, false);
            return None;
        }
    }

    Some(TaskRejected::new(
        "on wounded enemy tile, no safe step-off direction",
    ))
}
