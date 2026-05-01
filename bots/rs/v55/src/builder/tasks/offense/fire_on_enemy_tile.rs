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

pub fn fire_on_enemy_tile(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let vulnerable = vulnerable_harvesters(self_);
    if vulnerable.is_empty() {
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

    // Check for actual healing.
    let mut being_healed = false;
    if let Some((pos, expected_hp)) = self_.last_fire
        && pos == self_.my_pos
    {
        let bid_here = ct.get_tile_building_id(self_.my_pos).unwrap();
        if let Some(bid) = bid_here {
            let current_hp = ct.get_hp(Some(bid)).unwrap();
            if current_hp > expected_hp {
                being_healed = true;
            }
        }
    }

    let my_pos = self_.my_pos;

    if being_healed {
        self_.attack_tile_blacklist.insert(my_pos, 5);
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

    let bid_here = ct.get_tile_building_id(my_pos).unwrap();
    if let Some(bid) = bid_here {
        let pre_hp = ct.get_hp(Some(bid)).unwrap();
        self_.last_fire = Some((my_pos, (pre_hp - 2).max(0)));
    }
    try_attack(ct, my_pos);
    self_.offense_target = Some(my_pos);
    self_.offense_turns = 0;
    None
}
