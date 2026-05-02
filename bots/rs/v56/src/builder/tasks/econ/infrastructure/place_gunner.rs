//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/place_gunner.py`.
//!
//! Defensive gunner / sentinel placement adjacent to a friendly harvester.
//! Iterates DIR8 neighbours: gunner placement requires a forward-ray that
//! hits an enemy harvester or transport (via `gunner_facing`); sentinel
//! placement requires the nearest enemy turret to be within range
//! (`sentinel_facing`). Falls back to placing on `my_pos` after a random
//! step-off.

use cambc::{
    BuildExtra, Controller, ControllerApi, Direction, EntityType, GameConstants, Position, Team,
};

use crate::builder::Builder;
use crate::builder::helpers::{move_random, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::{DIR4, DIR8};

const fn is_turret(kind: Option<EntityType>) -> bool {
    matches!(
        kind,
        Some(EntityType::Gunner | EntityType::Sentinel | EntityType::Breach | EntityType::Launcher)
    )
}

const fn is_turret_or_transport(kind: Option<EntityType>) -> bool {
    matches!(
        kind,
        Some(
            EntityType::Gunner
                | EntityType::Sentinel
                | EntityType::Breach
                | EntityType::Launcher
                | EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
        )
    )
}

/// True if the building kind+team is a friendly building we must NOT
/// destroy when placing a turret.
fn is_precious_friendly(kind: Option<EntityType>, bteam: Option<Team>, team: Team) -> bool {
    if bteam != Some(team) {
        return false;
    }
    matches!(
        kind,
        Some(EntityType::Harvester | EntityType::Foundry | EntityType::Launcher)
    )
}

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

#[must_use]
pub fn gunner_facing(self_: &Builder, position: Position) -> Option<Direction> {
    if !pyrust::vec::contains!(self_.adjacent_to_harvester, &position) {
        return None;
    }
    if !self_.is_buildable(position) {
        return None;
    }
    let kind = self_.kind_at(position);
    let team = self_.team_at(position);
    if is_precious_friendly(kind, team, self_.my_team) {
        return None;
    }
    if is_turret(kind) {
        return None;
    }
    if let Some(&uid) = self_.all_bots.get(&position)
        && uid != self_.my_id
    {
        return None;
    }
    for d in DIR8 {
        let n = position.add(d);
        if !self_.in_bounds(n) {
            continue;
        }
        let nk = self_.kind_at(n);
        let nt = self_.team_at(n);
        let is_enemy_gunner_or_sentinel =
            matches!(nk, Some(EntityType::Gunner | EntityType::Sentinel))
                && pyrust::is_some!(nt)
                && nt != Some(self_.my_team);
        if !is_enemy_gunner_or_sentinel {
            continue;
        }
        for harvester_direction in DIR4 {
            if harvester_direction != d {
                let hn = position.add(harvester_direction);
                if !self_.in_bounds(hn) {
                    continue;
                }
                if self_.kind_at(hn) == Some(EntityType::Harvester) {
                    return Some(d);
                }
            }
        }
    }
    None
}

pub fn sentinel_facing(
    self_: &Builder,
    ct: &mut Controller<'_>,
    position: Position,
) -> Option<Direction> {
    let kind = self_.kind_at(position);
    let team = self_.team_at(position);
    let nearest = self_.nearest_enemy_turret;
    if pyrust::is_none!(nearest)
        || position.distance_squared(pyrust::unwrap!(nearest))
            > GameConstants::SENTINEL_VISION_RADIUS_SQ
        || !pyrust::vec::contains!(self_.adjacent_to_harvester, &position)
        || !self_.is_buildable(position)
        || is_turret_or_transport(kind)
        || is_precious_friendly(kind, team, self_.my_team)
        || !self_.in_bounds(position)
    {
        return None;
    }
    if let Some(&uid) = self_.all_bots.get(&position)
        && uid != self_.my_id
    {
        return None;
    }

    let nearest = pyrust::unwrap!(nearest);
    let d = direction_to(position, nearest);
    let mut found_harvester = false;
    for harvester_direction in DIR4 {
        if harvester_direction != d {
            let hn = position.add(harvester_direction);
            if !self_.in_bounds(hn) {
                continue;
            }
            if self_.kind_at(hn) == Some(EntityType::Harvester) {
                found_harvester = true;
            }
        }
    }
    if !found_harvester {
        return None;
    }

    let shootable_tiles =
        pyrust::unwrap!(ct.get_attackable_tiles_from(position, d, EntityType::Sentinel));
    if pyrust::vec::contains!(shootable_tiles, &nearest) {
        return Some(d);
    }
    None
}

pub fn place_sentinel_nearby(self_: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let neighbours_8 = pyrust::clone!(self_.neighbours_8);
    for test_position in neighbours_8 {
        let result = sentinel_facing(self_, ct, test_position);
        if let Some(d) = result {
            return try_place(
                self_,
                ct,
                EntityType::Sentinel,
                test_position,
                BuildExtra::Direction(d),
                true,
            );
        }
    }
    let my_pos = self_.my_pos;
    let result = sentinel_facing(self_, ct, my_pos);
    if let Some(d) = result
        && move_random(self_, ct)
    {
        try_place(
            self_,
            ct,
            EntityType::Sentinel,
            my_pos,
            BuildExtra::Direction(d),
            true,
        );
        return true;
    }
    false
}

pub fn place_gunner(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let neighbours_8 = pyrust::clone!(self_.neighbours_8);
    for test_position in neighbours_8 {
        let result = gunner_facing(self_, test_position);
        if let Some(d) = result {
            if try_place(
                self_,
                ct,
                EntityType::Gunner,
                test_position,
                BuildExtra::Direction(d),
                true,
            ) {
                return None;
            }
            return Some(TaskRejected::new(
                "no valid gunner or sentinel placement nearby",
            ));
        }
    }
    let my_pos = self_.my_pos;
    let result = gunner_facing(self_, my_pos);
    if let Some(d) = result
        && move_random(self_, ct)
    {
        try_place(
            self_,
            ct,
            EntityType::Gunner,
            my_pos,
            BuildExtra::Direction(d),
            true,
        );
        return None;
    }
    if place_sentinel_nearby(self_, ct) {
        return None;
    }
    Some(TaskRejected::new(
        "no valid gunner or sentinel placement nearby",
    ))
}
