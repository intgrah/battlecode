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
        return Err(TaskRejected::new(
            "low HP on enemy tile — fight to death, no heal",
        ));
    }
    if ct.get_hp(None).unwrap() > ct.get_max_hp(None).unwrap() - GameConstants::HEAL_AMOUNT {
        return Err(TaskRejected::new(
            "self HP within HEAL_AMOUNT of max — heal would waste Ti",
        ));
    }

    let my_pos = self_.my_pos;
    if !has_wounded_enemy(self_, my_pos) {
        try_heal(self_, ct, my_pos, false);
        move_random(self_, ct);
        return Ok(());
    }

    let dir_neighbours_8 = self_.dir_neighbours_8.clone();
    for (d, n) in dir_neighbours_8 {
        if ct.can_move(d).unwrap() && !has_wounded_enemy(self_, n) {
            ct.move_(d).unwrap();
            let cur = ct.get_position(None).unwrap();
            try_heal(self_, ct, cur, false);
            return Ok(());
        }
    }

    Err(TaskRejected::new(
        "on wounded enemy tile, no safe step-off direction",
    ))
}
