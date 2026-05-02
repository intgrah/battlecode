//! Defensive turret-clearing task.
//!
//! Looks for enemy turrets (Launcher, Sentinel, Gunner, Breach) that are
//! within sentinel attack range of one of our own dangling chain tips.
//! Places a sentinel at the dangling tip facing the enemy turret. The
//! dangling tip is already on our flow chain (that's the definition of
//! `dangling_set`), so the placed sentinel will receive ammo via the
//! existing chain — no new feeder construction needed.
//!
//! Differs from `place_offensive_sentinel` (in `tasks/offense/push/`):
//! - Restricted to dangling tips in OUR half (defensive vs push).
//! - Targets only enemy turrets, not transports.
//! - Higher pipeline priority (above `stalk_enemy`) — kill the launcher
//!   first, chase the enemy bot second.

use cambc::{BuildExtra, Controller, ControllerApi, Direction, EntityType, Environment, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, make_move, move_random, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR8;
use crate::util::metrics::chebyshev;
use crate::util::posint::{DIR8_INT, dist_sq, idx_of, pos_of};

/// Only enemy turrets count — defensive task targets the actual threat.
fn is_enemy_turret(self_: &Builder, pos: Position) -> bool {
    let Some((kind, team)) = self_.get_building(pos) else {
        return false;
    };
    if team == self_.my_team {
        return false;
    }
    matches!(
        kind,
        EntityType::Launcher | EntityType::Sentinel | EntityType::Gunner | EntityType::Breach
    )
}

/// `side` is a deliverer for a sentinel at `pos` iff it's a structural
/// feeder of `pos` or a friendly **Ti** harvester. Ax harvesters output
/// raw Ax which sentinels can't use as ammo — wrongly counting them as
/// deliverers loses a potential enemy-attack facing.
fn delivers_ammo(self_: &Builder, pos: Position, side: Position) -> bool {
    let in_edges = &self_.in_edges[idx_of(pos) as usize];
    if pyrust::vec::contains!(in_edges, &side) {
        return true;
    }
    let i = idx_of(side) as usize;
    self_.building_kind[i] == Some(EntityType::Harvester)
        && self_.building_team[i] == Some(self_.my_team)
        && self_.env[i] == Some(Environment::OreTitanium)
}

fn sentinel_facing(self_: &Builder, ct: &mut Controller<'_>, pos: Position) -> Option<Direction> {
    let pos_p = idx_of(pos);
    for ii in 0..8usize {
        let d = DIR8[ii];
        let dp = DIR8_INT[ii];
        let fp = pos_p + dp;
        if fp >= 0 && self_.posint_valid[fp as usize] != 0 && delivers_ammo(self_, pos, pos_of(fp))
        {
            continue;
        }
        let tiles = pyrust::unwrap!(ct.get_attackable_tiles_from(pos, d, EntityType::Sentinel));
        for t in tiles {
            if is_enemy_turret(self_, t) {
                return Some(d);
            }
        }
    }
    None
}

pub fn clear_enemy_turret(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !can_afford(self_, EntityType::Sentinel) {
        return Some(TaskRejected::new("cannot afford SENTINEL"));
    }

    let mut best_pos: Option<Position> = None;
    let mut best_facing: Option<Direction> = None;
    let mut best_dist = 1 << 30;
    let my_p = idx_of(self_.my_pos);
    let dangling = pyrust::clone!(self_.dangling_set);
    for pi in dangling {
        let pos = pos_of(pi);
        // Defensive scope: only dangling tips in OUR half. Skip those that
        // are closer to the enemy core than to ours — the offensive
        // variant covers those.
        if chebyshev(pos, self_.en_core_guess) < chebyshev(pos, self_.my_core) {
            continue;
        }
        if !self_.is_buildable_p(pi) {
            continue;
        }
        if let Some(&uid) = self_.all_bots.get(&pos)
            && uid != self_.my_id
        {
            continue;
        }
        let Some(facing) = sentinel_facing(self_, ct, pos) else {
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
            "no dangling end in our half with enemy turret in sentinel range",
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
