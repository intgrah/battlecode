//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/fire_on_enemy_tile.py`.
//!
//! Standing on an enemy building cardinal to a vulnerable enemy
//! harvester: fire on it (2 Ti for 2 dmg). Tracks `last_fire = (pos,
//! expected_hp)` so a future visit can detect enemy heals.

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;
use crate::builder::helpers::{make_move, try_attack};
use crate::builder::tasks::offense::helpers::{
    is_allied_transport, pick_attack_destination, pick_harvester_target, should_attack,
    vulnerable_harvesters,
};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::posint::idx_of;

pub fn fire_on_enemy_tile(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let vulnerable = vulnerable_harvesters(self_);
    if pyrust::vec::is_empty!(vulnerable) {
        return Some(TaskRejected::new(
            "not cardinally adjacent to a vulnerable harvester",
        ));
    }
    let target = pick_harvester_target(self_, &vulnerable);
    if self_.my_pos.distance_squared(target) != 1 {
        return Some(TaskRejected::new(
            "not cardinally adjacent to a vulnerable harvester",
        ));
    }

    if is_allied_transport(self_, self_.my_pos) {
        return Some(TaskRejected::new(
            "standing on friendly transport — fire would break own chain",
        ));
    }
    if !self_.is_enemy_building(self_.my_pos) {
        return Some(TaskRejected::new("not standing on an enemy building"));
    }

    // Check for actual healing — use cached hp/building_ids to avoid
    // two Python-boundary ct calls (get_tile_building_id + get_hp).
    let my_pos_i = idx_of(self_.my_pos) as usize;
    let mut being_healed = false;
    if let Some((pos, expected_hp)) = self_.last_fire
        && pos == self_.my_pos
        && self_.building_ids[my_pos_i].is_some()
    {
        let current_hp = self_.hp[my_pos_i];
        if current_hp > expected_hp {
            being_healed = true;
        }
    }

    let my_pos = self_.my_pos;

    if being_healed {
        pyrust::dict::insert!(self_.attack_tile_blacklist, idx_of(my_pos), 5);
        self_.last_fire = None;
        let alt = pick_attack_destination(self_, target, true);
        if let Some(a) = alt
            && a != my_pos
        {
            make_move(self_, ct, a);
        }
        self_.offense_target = Some(my_pos);
        self_.offense_turns = 0;
        return None;
    }

    if !should_attack(self_, my_pos) {
        self_.last_fire = None;
        let alt = pick_attack_destination(self_, target, true);
        if let Some(a) = alt
            && a != my_pos
        {
            make_move(self_, ct, a);
        }
        self_.offense_target = Some(my_pos);
        self_.offense_turns = 0;
        return None;
    }

    // Use cached building_ids + hp to avoid two Python-boundary ct calls.
    if self_.building_ids[my_pos_i].is_some() {
        let pre_hp = self_.hp[my_pos_i];
        self_.last_fire = Some((my_pos, pyrust::max!((pre_hp - 2), 0)));
    }
    try_attack(ct, my_pos);
    self_.offense_target = Some(my_pos);
    self_.offense_turns = 0;
    None
}
