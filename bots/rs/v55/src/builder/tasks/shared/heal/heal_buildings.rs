//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/heal_buildings.py`.
//!
//! Heal a damaged friendly building. Picks a `repair_pos` (committed
//! target) via `_best_healable_building`'s deconflicted scoring, walks
//! toward it, and tries `try_heal` on the best in-range tile both before
//! and after the move. Mutates `self.repair_pos` and `self.repaired_prev`
//! for cross-turn continuity. Buildings have explicit movement; bot-heal
//! leaves do not.

use cambc::{Controller, ControllerApi, Position};

use crate::builder::Builder;
use crate::builder::helpers::{make_move, try_heal};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::builder::tasks::shared::heal::_helpers::{
    count_visible_attackers, deconflict_rank, healers_needed,
};
use crate::util::metrics::chebyshev;

/// Pick the most valuable reachable damaged friendly building with
/// attacker-aware deconfliction and priority for harvester-adjacent
/// infrastructure.
fn best_healable_building(self_: &mut Builder, ct: &mut Controller<'_>) -> Option<Position> {
    let mut best: Option<Position> = None;
    let mut best_score: (i32, i32, i32) = (0, 0, 0);
    let healable = self_.healable_buildings.clone();
    for pos in healable {
        let i = self_.idx(pos);
        let hp = self_.hp[i];
        let max_hp = self_.max_hp[i];
        let damage = max_hp - hp;
        if damage <= 0 {
            continue;
        }

        let attackers = count_visible_attackers(self_, pos);
        let needed = healers_needed(attackers);
        let rank = deconflict_rank(self_, ct, self_.my_pos, pos);
        if rank >= needed {
            if !pyrust::unwrap!(ct.is_in_vision(pos)) {
                self_.hp[i] = max_hp;
            }
            continue;
        }

        let dist = chebyshev(self_.my_pos, pos);
        let turns_to_reach = (dist - 1).max(0);
        let dmg_per_turn = (attackers * 2).max(2);
        let turns_to_die = (hp / dmg_per_turn).max(1);
        let can_reach = turns_to_reach <= turns_to_die + 1;
        let is_critical = self_.adjacent_to_harvester.contains(&pos);

        let tier = if is_critical && can_reach {
            3
        } else if damage >= 4 && can_reach {
            2
        } else if damage >= 4 {
            1
        } else {
            0
        };
        let score = (tier, damage, turns_to_die - turns_to_reach);

        if score > best_score {
            best = Some(pos);
            best_score = score;
        }
    }
    self_.healable_buildings = self_
        .healable_buildings
        .iter()
        .copied()
        .filter(|&p| self_.hp[self_.idx(p)] < self_.max_hp[self_.idx(p)])
        .collect();
    best
}

/// Damaged friendly building within heal range (d²<=2). Two-tier
/// score: prefer 4+-damage tiles over chip damage; within each tier,
/// prefer larger damage.
fn best_adjacent_healable_building(self_: &Builder) -> Option<Position> {
    let mut best: Option<Position> = None;
    let mut best_score: (i32, i32) = (0, 0);
    for &pos in &self_.healable_buildings {
        let i = self_.idx(pos);
        let hp = self_.hp[i];
        let max_hp = self_.max_hp[i];
        let damage = max_hp - hp;
        if self_.my_pos.distance_squared(pos) > 2 {
            continue;
        }
        let score = if damage < 4 { (0, damage) } else { (1, damage) };
        if score > best_score {
            best = Some(pos);
            best_score = score;
        }
    }
    best
}

pub fn heal_buildings(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if let Some(rp) = self_.repair_pos
        && pyrust::unwrap!(ct.is_in_vision(rp))
    {
        let ti_idx = self_.idx(rp);
        if let Some((_kind, team)) = self_.get_building(rp)
            && self_.hp[ti_idx] < self_.max_hp[ti_idx] - 2
            && team == self_.my_team
        {
            // keep
        } else {
            self_.repair_pos = None;
        }
    }
    let new_repair = best_healable_building(self_, ct);
    if (pyrust::is_some!(new_repair) && pyrust::unwrap!(new_repair).distance_squared(self_.my_pos) <= 2)
        || pyrust::is_none!(self_.repair_pos)
    {
        self_.repair_pos = new_repair;
    }

    let Some(repair_pos) = self_.repair_pos else {
        return Some(TaskRejected::new(
            "no damaged friendly building worth healing right now",
        ));
    };

    let heal_position = repair_pos;
    let being_attacked = self_.enemy_bots.contains(&heal_position);

    let building_to_heal = best_adjacent_healable_building(self_);
    let save_money = being_attacked && self_.repaired_prev;
    if let Some(bpos) = building_to_heal {
        self_.repaired_prev = try_heal(self_, ct, bpos, save_money);
    } else {
        self_.repaired_prev = false;
    }
    make_move(self_, ct, heal_position);
    let building_to_heal = best_adjacent_healable_building(self_);
    if let Some(bpos) = building_to_heal {
        self_.repaired_prev = try_heal(self_, ct, bpos, save_money) || self_.repaired_prev;
    }
    None
}
