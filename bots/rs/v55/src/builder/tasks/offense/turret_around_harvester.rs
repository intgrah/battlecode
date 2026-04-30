//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/turret_around_harvester.py`.
//!
//! Place gunner / sentinel turrets adjacent to a vulnerable enemy
//! harvester, capping at 2 gunners + 1 sentinel per harvester.

use cambc::{BuildExtra, Controller, ControllerApi, Direction, EntityType, Environment, Position};

use crate::builder::Builder;
use crate::builder::helpers::{move_random, try_place};
use crate::builder::tasks::offense::helpers::{
    gunner_chain_facing, is_allied_transport, pick_harvester_target, scout_toward_enemy,
    vulnerable_harvesters,
};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::building::Building;
use crate::util::directions::DIR4;

/// Snap the unit vector from `from` to `to` to the nearest 45-degree direction.
fn direction_to(from: Position, to: Position) -> Direction {
    let dx = to.x - from.x;
    let dy = to.y - from.y;
    if dx == 0 && dy == 0 {
        return Direction::Centre;
    }
    let angle = (-(dy as f64)).atan2(dx as f64);
    let raw = (angle + 2.0 * std::f64::consts::PI + std::f64::consts::FRAC_PI_8)
        / std::f64::consts::FRAC_PI_4;
    let sector = (raw as i32).rem_euclid(8) as usize;
    [
        Direction::East,
        Direction::Northeast,
        Direction::North,
        Direction::Northwest,
        Direction::West,
        Direction::Southwest,
        Direction::South,
        Direction::Southeast,
    ][sector]
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
    if vulnerable.is_empty() {
        return Err(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    let target = pick_harvester_target(self_, &vulnerable);
    if self_.my_pos.distance_squared(target) != 1 {
        return Err(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    if is_allied_transport(self_, self_.my_pos) {
        return Err(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }
    if self_.is_enemy_building(self_.my_pos) {
        return Err(TaskRejected::new(
            "not on empty terrain cardinal to a vulnerable harvester",
        ));
    }

    let build_position = self_.my_pos;
    let enemy_core = self_.en_core_guess;
    move_random(self_, ct);
    let mut direction = direction_to(build_position, enemy_core);
    if direction == direction_to(build_position, target) {
        direction = rotate_right(direction);
    }

    let mut n_gunner = 0;
    let mut n_sentinel = 0;
    for d in DIR4 {
        let n = target.add(d);
        if !self_.in_bounds(n) {
            continue;
        }
        let nb = self_.get_building(n);
        let Some(nb) = nb else { continue };
        if nb.team() != self_.my_team {
            continue;
        }
        if matches!(nb, Building::Gunner { .. }) {
            n_gunner += 1;
        } else if matches!(nb, Building::Sentinel { .. }) {
            n_sentinel += 1;
        }
    }

    if n_gunner < 2 {
        let gdir = gunner_chain_facing(self_, build_position);
        if let Some(gd) = gdir {
            try_place(
                self_,
                ct,
                EntityType::Gunner,
                build_position,
                BuildExtra::Direction(gd),
                true,
            );
        }
    }

    if n_sentinel == 0 && self_.get_env(target) == Some(Environment::OreTitanium) {
        try_place(
            self_,
            ct,
            EntityType::Sentinel,
            build_position,
            BuildExtra::Direction(direction),
            true,
        );
    }

    if ct.can_build_road(build_position).unwrap() {
        ct.build_road(build_position).unwrap();
    }
    scout_toward_enemy(self_, ct);
    Ok(())
}
