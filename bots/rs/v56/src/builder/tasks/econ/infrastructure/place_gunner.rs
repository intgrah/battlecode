//! Defensive gunner / sentinel placement adjacent to a friendly harvester.
//! Iterates DIR8 neighbours: gunner placement requires a forward-ray that
//! hits an enemy harvester or transport (via `gunner_facing`); sentinel
//! placement requires the nearest enemy turret to be within range
//! (`sentinel_facing`). Falls back to placing on `my_pos` after a random
//! step-off.

use cambc::{
    BuildExtra, Controller, ControllerApi, Direction, EntityType, Environment, GameConstants,
    Position, ResourceType, Team,
};

use crate::builder::Builder;
use crate::builder::helpers::{move_random, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::{DIR4, DIR8, is_cardinal, rotate_right};

const fn is_turret(kind: Option<EntityType>) -> bool {
    matches!(
        kind,
        Some(EntityType::Gunner | EntityType::Sentinel | EntityType::Breach | EntityType::Launcher)
    )
}

pub const fn is_resource_building(kind: Option<EntityType>) -> bool {
    matches!(
        kind,
        Some(
            EntityType::Harvester
                | EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
                | EntityType::Bridge
                | EntityType::Foundry
        )
    )
}

/// If `d` faces directly into a friendly resource building adjacent to `pos`,
/// rotate it one step clockwise.
pub fn safe_facing(self_: &Builder, pos: Position, d: Direction) -> Direction {
    if !is_cardinal(d) {
        return d;
    }
    let front = pos.add(d);
    if self_.in_bounds(front)
        && is_resource_building(self_.kind_at(front))
        && self_.team_at(front) == Some(self_.state.my_team)
    {
        return rotate_right(d);
    }
    d
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

const fn _is_cardinal(d: Direction) -> bool {
    matches!(
        d,
        Direction::North | Direction::South | Direction::East | Direction::West
    )
}

/// True iff `pos` has Ti flowing in from a non-facing side. Sources:
/// 1. Friendly Ti harvester cardinal of `pos` (direct ore output).
/// 2. An `in_edges[pos]` transport carrying Ti — structurally
///    (`ti_upstream`) OR empirically (`flow_history` contains Ti).
/// Cardinal-facing turrets reject ammo from the facing cardinal;
/// diagonal-facing turrets accept from all 4 cardinals (so we don't
/// exclude any when `facing` is diagonal).
#[must_use]
fn _feedable(self_: &Builder, pos: Position, facing: Direction) -> bool {
    let facing_pos = if _is_cardinal(facing) {
        Some(pos.add(facing))
    } else {
        None
    };
    // Source 1: direct Ti harvester output.
    for d in DIR4 {
        let c = pos.add(d);
        if pyrust::is_some_and!(facing_pos, |fp: Position| fp == c) {
            continue;
        }
        if !self_.in_bounds(c) {
            continue;
        }
        if self_.kind_at(c) == Some(EntityType::Harvester)
            && self_.team_at(c) == Some(self_.my_team)
            && self_.get_env(c) == Some(Environment::OreTitanium)
        {
            return true;
        }
    }
    // Source 2: Ti-carrying transport in_edge.
    let i = self_.idx(pos);
    let in_edges_clone: Vec<Position> = pyrust::clone!(self_.in_edges[i]);
    for f in &in_edges_clone {
        if pyrust::is_some_and!(facing_pos, |fp: Position| fp == *f) {
            continue;
        }
        if pyrust::vec::contains!(self_.ti_upstream, f) {
            return true;
        }
        let fi = self_.idx(*f);
        for (r, _) in &self_.flow_history[fi] {
            if *r == Some(ResourceType::Titanium) {
                return true;
            }
        }
    }
    false
}

/// Pick a facing direction at `position` that targets an enemy turret
/// in `enemy_turrets` AND leaves the placement spot feedable. Replaces
/// the older harvester-adjacency rule: any visible enemy Gunner /
/// Sentinel / Launcher / Breach is a valid trigger.
#[must_use]
pub fn gunner_facing(
    self_: &Builder,
    ct: &mut Controller<'_>,
    position: Position,
) -> Option<Direction> {
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
    let r2 = GameConstants::GUNNER_VISION_RADIUS_SQ;
    let turrets = pyrust::clone!(self_.enemy_turrets);
    for t in &turrets {
        if position.distance_squared(*t) > r2 {
            continue;
        }
        let d = direction_to(position, *t);
        if matches!(d, Direction::Centre) {
            continue;
        }
        let attackable =
            pyrust::unwrap!(ct.get_attackable_tiles_from(position, d, EntityType::Gunner));
        if !pyrust::vec::contains!(attackable, t) {
            continue;
        }
        if !_feedable(self_, position, d) {
            continue;
        }
        return Some(d);
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

    if is_cardinal(d) {
        let front = position.add(d);
        if self_.in_bounds(front)
            && is_resource_building(self_.kind_at(front))
            && self_.team_at(front) == Some(self_.state.my_team)
        {
            return None;
        }
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
        let result = gunner_facing(self_, ct, test_position);
        if let Some(d) = result {
            let d = safe_facing(self_, test_position, d);
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
    let result = gunner_facing(self_, ct, my_pos);
    if let Some(d) = result
        && move_random(self_, ct)
    {
        let d = safe_facing(self_, my_pos, d);
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
