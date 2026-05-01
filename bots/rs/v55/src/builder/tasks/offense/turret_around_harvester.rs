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
use crate::util::directions::DIR4;

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
    match (pyrust::signum!(dx), pyrust::signum!(dy)) {
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
        let Some((nk, nt)) = self_.get_building(n) else {
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

    if pyrust::unwrap!(ct.can_build_road(build_position)) {
        pyrust::unwrap!(ct.build_road(build_position));
    }
    scout_toward_enemy(self_, ct);
    None
}
