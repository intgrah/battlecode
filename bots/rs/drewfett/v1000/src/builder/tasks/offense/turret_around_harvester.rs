//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/turret_around_harvester.py`.
//!
//! Place gunner / sentinel turrets adjacent to a vulnerable enemy
//! harvester, capping at 2 gunners + 1 sentinel per harvester.

use cambc::{BuildExtra, Controller, ControllerApi, Direction, EntityType, Environment, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, move_random, try_place};
use crate::builder::tasks::econ::infrastructure::place_gunner::{
    blocks_ax_harvester, is_resource_building,
};
use crate::builder::tasks::offense::converge_on_rendezvous::place_marker_best_effort;
use crate::builder::tasks::offense::helpers::{
    friendly_bot_adjacent, gunner_chain_facing, is_allied_transport, pick_harvester_target,
    scout_toward_enemy, vulnerable_harvesters,
};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::marker::{Marker, decode, encode, round_lo};
use crate::util::directions::is_cardinal;
use crate::util::posint::{DIR4_INT, idx_of};

/// Snap the unit vector from `src` to `dst` to the nearest 45-degree direction.
const fn direction_to(src: Position, dst: Position) -> Direction {
    let dx = dst.x - src.x;
    let dy = dst.y - src.y;
    if dx == 0 && dy == 0 {
        return Direction::Centre;
    }
    let adx = pyrust::abs!(dx);
    let ady = pyrust::abs!(dy);
    if adx * 5 < ady * 2 {
        return if dy < 0 {
            Direction::North
        } else {
            Direction::South
        };
    }
    if ady * 5 < adx * 2 {
        return if dx < 0 {
            Direction::West
        } else {
            Direction::East
        };
    }
    let sx = (dx > 0) as i32 - (dx < 0) as i32;
    let sy = (dy > 0) as i32 - (dy < 0) as i32;
    match (sx, sy) {
        (1, -1) => Direction::Northeast,
        (1, 1) => Direction::Southeast,
        (-1, 1) => Direction::Southwest,
        (-1, -1) => Direction::Northwest,
        _ => Direction::Centre,
    }
}

const fn rotate_right(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::Northeast,
        Direction::Northeast => Direction::East,
        Direction::East => Direction::Southeast,
        Direction::Southeast => Direction::South,
        Direction::South => Direction::Southwest,
        Direction::Southwest => Direction::West,
        Direction::West => Direction::Northwest,
        Direction::Northwest => Direction::North,
        Direction::Centre => Direction::Centre,
    }
}

pub fn turret_around_harvester(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let vulnerable = vulnerable_harvesters(self_);
    if pyrust::vec::is_empty!(vulnerable) {
        return Some(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    let target = pick_harvester_target(self_, &vulnerable);
    if self_.my_pos.distance_squared(target) != 1 {
        return Some(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    if is_allied_transport(self_, self_.my_pos) {
        return Some(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    if self_.is_enemy_building(self_.my_pos) {
        return Some(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    // Don't place a turret cardinal to our own Ax harvester — would
    // intercept raw Ax flow to the foundry.
    if blocks_ax_harvester(self_, self_.my_pos) {
        return Some(TaskRejected::new("would block friendly Ax harvester feed"));
    }

    let build_position = self_.my_pos;
    let enemy_core = self_.en_core_guess;

    let mut direction = direction_to(build_position, enemy_core);
    if direction == direction_to(build_position, target) {
        direction = rotate_right(direction);
    }

    let mut n_gunner = 0;
    let mut n_sentinel = 0;
    let target_p = idx_of(target);
    for &dp in &DIR4_INT {
        let np = target_p + dp;
        if np < 0 || self_.posint_valid[np as usize] == 0 {
            continue;
        }
        let Some((nk, nt)) = self_.get_building_p(np) else {
            continue;
        };
        if nt != self_.my_team {
            continue;
        }
        if nk == EntityType::Gunner {
            n_gunner += 1;
        } else if nk == EntityType::Sentinel {
            n_sentinel += 1;
        }
    }

    let gdir = if n_gunner < 2 {
        gunner_chain_facing(self_, build_position)
    } else {
        None
    };
    let want_gunner = pyrust::is_some!(gdir) && can_afford(self_, EntityType::Gunner);
    // Don't sentinel-block our own resource building when sentinel direction
    // is cardinal toward it (sentinel cone would block ammo/Ti routing).
    let sentinel_dir_ok = !is_cardinal(direction)
        || !self_.in_bounds(build_position.add(direction))
        || !is_resource_building(self_.kind_at(build_position.add(direction)))
        || self_.team_at(build_position.add(direction)) != Some(self_.my_team);
    let want_sentinel = sentinel_dir_ok
        && n_sentinel == 0
        && self_.get_env_p(target_p) == Some(Environment::OreTitanium)
        && can_afford(self_, EntityType::Sentinel);

    let mut placed = false;
    if want_gunner || want_sentinel {
        move_random(self_, ct);
        if want_gunner {
            placed = try_place(
                self_,
                ct,
                EntityType::Gunner,
                build_position,
                BuildExtra::Direction(pyrust::unwrap!(gdir)),
                true,
            );
        }
        if !placed && want_sentinel {
            placed = try_place(
                self_,
                ct,
                EntityType::Sentinel,
                build_position,
                BuildExtra::Direction(direction),
                true,
            );
        }
    }

    if !placed {
        if pyrust::unwrap!(ct.can_build_road(build_position)) {
            pyrust::unwrap!(ct.build_road(build_position));
        } else {
            return Some(TaskRejected::new("couldn't place a turret or road"));
        }
    }

    scout_toward_enemy(self_, ct);
    None
}
