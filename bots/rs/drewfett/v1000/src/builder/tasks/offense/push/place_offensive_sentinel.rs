//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/place_offensive_sentinel.py`.
//!
//! Drop a sentinel on a dangling end whose attack ray reaches a valuable
//! enemy structure. Candidates come from `dangling_set` (chain tips, never
//! existing conveyors).

use cambc::{BuildExtra, Controller, ControllerApi, Direction, EntityType, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, make_move, move_random, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR8;
use crate::util::posint::{DIR8_INT, dist_sq, idx_of, pos_of};

/// Sentinel-worthy enemy targets.
fn is_enemy_valuable(self_: &Builder, pos: Position) -> bool {
    let Some((kind, team)) = self_.get_building(pos) else {
        return false;
    };
    if team == self_.my_team {
        return false;
    }
    if kind == EntityType::Harvester {
        return false;
    }
    matches!(
        kind,
        EntityType::Conveyor
            | EntityType::ArmouredConveyor
            | EntityType::Splitter
            | EntityType::Bridge
            | EntityType::Core
            | EntityType::Gunner
            | EntityType::Sentinel
            | EntityType::Breach
            | EntityType::Launcher
    )
}

/// `side` is a deliverer for a turret at `pos` iff it's a structural
/// feeder of `pos` or a friendly harvester.
fn delivers_ammo(self_: &Builder, pos: Position, side: Position) -> bool {
    let in_edges = &self_.in_edges[idx_of(pos) as usize];
    if pyrust::vec::contains!(in_edges, &side) {
        return true;
    }
    self_.kind_at(side) == Some(EntityType::Harvester) && self_.team_at(side) == Some(self_.my_team)
}

/// First DIR8 direction such that a sentinel at `pos` facing `d`
/// has at least one valuable enemy in its attack ray AND has no
/// feeder on the tile in direction `d`.
fn sentinel_facing(self_: &Builder, ct: &mut Controller<'_>, pos: Position) -> Option<Direction> {
    let pos_p = idx_of(pos);
    for ii in 0..8usize {
        let d = DIR8[ii];
        let dp = DIR8_INT[ii];
        let fp = pos_p + dp;
        if fp >= 0
            
            && self_.posint_valid[fp as usize] != 0
            && delivers_ammo(self_, pos, pos_of(fp))
        {
            continue;
        }
        let tiles = pyrust::unwrap!(ct.get_attackable_tiles_from(pos, d, EntityType::Sentinel));
        for t in tiles {
            if is_enemy_valuable(self_, t) {
                return Some(d);
            }
        }
    }
    None
}

pub fn place_offensive_sentinel(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !can_afford(self_, EntityType::Sentinel) {
        return Some(TaskRejected::new("cannot afford SENTINEL"));
    }

    let mut best_pos: Option<Position> = None;
    let mut best_facing: Option<Direction> = None;
    let mut best_dist = 1 << 30;
    let my_p = idx_of(self_.my_pos);
    let dangling = pyrust::clone!(self_.dangling_set);
    for pi in dangling {
        if !self_.is_buildable_p(pi) {
            continue;
        }
        let pos = pos_of(pi);
        if let Some(&uid) = self_.all_bots.get(&pos)
            && uid != self_.my_id
        {
            continue;
        }
        let facing = sentinel_facing(self_, ct, pos);
        let Some(facing) = facing else {
            continue;
        };
        let d = dist_sq(my_p, pi);
        if d < best_dist {
            best_dist = d;
            best_pos = Some(pos);
            best_facing = Some(facing);
        }
    }

    let (Some(best_pos), Some(best_facing)) = (best_pos, best_facing) else {
        return Some(TaskRejected::new(
            "no dangling end with an enemy in sentinel range",
        ));
    };

    if self_.my_pos == best_pos {
        move_random(self_, ct);
        return None;
    }
    if self_.my_pos.distance_squared(best_pos) <= 2 {
        try_place(
            self_,
            ct,
            EntityType::Sentinel,
            best_pos,
            BuildExtra::Direction(best_facing),
            true,
        );
        return None;
    }
    make_move(self_, ct, best_pos);
    None
}
