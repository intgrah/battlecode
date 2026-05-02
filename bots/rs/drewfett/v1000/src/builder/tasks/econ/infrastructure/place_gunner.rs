//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/place_gunner.py`.
//!
//! Defensive gunner / sentinel placement adjacent to a friendly harvester.
//! Iterates DIR8 neighbours: gunner placement requires a forward-ray that
//! hits an enemy harvester or transport (via `gunner_facing`); sentinel
//! placement requires the nearest enemy turret to be within range
//! (`sentinel_facing`). Falls back to placing on `my_pos` after a random
//! step-off.

use cambc::{BuildExtra, Controller, ControllerApi, Direction, EntityType, Position, Team};

use crate::builder::Builder;
use crate::builder::helpers::{move_random, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::{DIR4, DIR8};
use crate::util::posint::{DIR4_INT, DIR8_INT, idx_of};

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

#[must_use]
pub fn gunner_facing(self_: &Builder, position: Position) -> Option<Direction> {
    let p = idx_of(position);
    if !pyrust::vec::contains!(self_.adjacent_to_harvester, &p) {
        return None;
    }
    if !self_.is_buildable(position) {
        return None;
    }
    let kind = self_.kind_at_p(p);
    let team = self_.team_at_p(p);
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
    for ii in 0..8usize {
        let d = DIR8[ii];
        let di = DIR8_INT[ii];
        let np = p + di;
        if np < 0 || self_.posint_valid[np as usize] == 0 {
            continue;
        }
        let nk = self_.kind_at_p(np);
        let nt = self_.team_at_p(np);
        let is_enemy_gunner_or_sentinel =
            matches!(nk, Some(EntityType::Gunner | EntityType::Sentinel))
                && pyrust::is_some!(nt)
                && nt != Some(self_.my_team);
        if !is_enemy_gunner_or_sentinel {
            continue;
        }
        for ji in 0..4usize {
            let harvester_direction = DIR4[ji];
            let hdi = DIR4_INT[ji];
            if harvester_direction != d {
                let hnp = p + hdi;
                if hnp < 0 || self_.posint_valid[hnp as usize] == 0 {
                    continue;
                }
                if self_.kind_at_p(hnp) == Some(EntityType::Harvester) {
                    return Some(d);
                }
            }
        }
    }
    None
}

/// Per-tile enemy value for sentinel scoring. Roads / barriers / markers
/// are excluded — destroying them just makes the enemy rebuild for ~1 Ti.
fn enemy_value_at(builder: &Builder, pos: Position) -> i32 {
    if !builder.in_bounds(pos) {
        return 0;
    }
    let mut score = 0;
    if let Some((kind, team)) = builder.get_building(pos)
        && team != builder.my_team
    {
        let kind_score = if kind == EntityType::Core {
            50
        } else if matches!(
            kind,
            EntityType::Launcher | EntityType::Gunner | EntityType::Sentinel | EntityType::Breach
        ) {
            10
        } else if kind == EntityType::Foundry {
            6
        } else if kind == EntityType::Harvester {
            5
        } else if kind == EntityType::Bridge {
            4
        } else if matches!(kind, EntityType::Splitter | EntityType::ArmouredConveyor) {
            3
        } else if kind == EntityType::Conveyor {
            2
        } else {
            0
        };
        score += kind_score;
    }
    if pyrust::vec::contains!(builder.state.enemy_bots, &pos) {
        score += 2;
    }
    score
}

/// Don't sentinel-spam when broke. Sentinel base cost is 30 Ti; we
/// keep a buffer so we can still spawn / extend chains.
const TI_GATE: i32 = 150;
/// Net-score floor: enough enemy value in cone to justify 30 Ti.
/// 10 ≈ 1 turret OR 1 harvester + 1 bridge OR 1 harvester + 2 conveyors
/// OR 5 enemy conveyors (worth ~15 Ti to enemy).
const MIN_NET_SCORE: i32 = 10;
/// Saturation: don't pile up sentinels next to each other.
const SATURATION_RADIUS: i32 = 5;

pub fn sentinel_facing(
    self_: &Builder,
    ct: &mut Controller<'_>,
    position: Position,
) -> Option<Direction> {
    if self_.state.ti < TI_GATE {
        return None;
    }
    let p = idx_of(position);
    if p < 0 || self_.posint_valid[p as usize] == 0 {
        return None;
    }
    if !pyrust::vec::contains!(self_.adjacent_to_harvester, &p) {
        return None;
    }
    if !self_.is_buildable(position) {
        return None;
    }
    let kind = self_.kind_at_p(p);
    let team = self_.team_at_p(p);
    if is_turret_or_transport(kind) || is_precious_friendly(kind, team, self_.my_team) {
        return None;
    }
    if let Some(&uid) = self_.all_bots.get(&position)
        && uid != self_.my_id
    {
        return None;
    }

    // Saturation check: skip if we already have a friendly sentinel
    // covering the same area.
    for t in &self_.state.nearby_tiles {
        if let Some((nt_kind, nt_team)) = self_.get_building(*t)
            && nt_kind == EntityType::Sentinel
            && nt_team == self_.my_team
        {
            let cheb = pyrust::max!(
                pyrust::abs!((t.x - position.x)),
                pyrust::abs!((t.y - position.y))
            );
            if cheb <= SATURATION_RADIUS {
                return None;
            }
        }
    }

    // Cheap precheck: any worthwhile enemy in the WHOLE vision? If not,
    // no cone can clear the threshold.
    let mut total_visible_enemy = 0i32;
    for t in &self_.state.nearby_tiles {
        total_visible_enemy += enemy_value_at(self_, *t);
        if total_visible_enemy >= MIN_NET_SCORE {
            break;
        }
    }
    if total_visible_enemy < MIN_NET_SCORE {
        return None;
    }

    // Per-direction cone scoring. Take the best direction whose cone
    // clears MIN_NET_SCORE.
    let mut best_dir: Option<Direction> = None;
    let mut best_score: i32 = 0;
    for ii in 0..8usize {
        let d = DIR8[ii];
        let di = DIR8_INT[ii];
        // Feeder: harvester adjacent in a non-facing cardinal direction.
        let mut found_harvester = false;
        for ji in 0..4usize {
            let hd = DIR4[ji];
            let hdi = DIR4_INT[ji];
            if hd == d {
                continue;
            }
            let hnp = p + hdi;
            if hnp < 0 || self_.posint_valid[hnp as usize] == 0 {
                continue;
            }
            if self_.kind_at_p(hnp) == Some(EntityType::Harvester) {
                found_harvester = true;
                break;
            }
        }
        if !found_harvester {
            continue;
        }

        let Some(shootable) = Some(pyrust::unwrap!(ct.get_attackable_tiles_from(
            position,
            d,
            EntityType::Sentinel
        ))) else {
            continue;
        };
        let mut score = 0i32;
        for t in pyrust::iter!(shootable) {
            score += enemy_value_at(self_, *t);
            if score >= MIN_NET_SCORE * 2 {
                break;
            }
        }
        if score > best_score {
            best_score = score;
            best_dir = Some(d);
        }
    }

    if best_score >= MIN_NET_SCORE {
        best_dir
    } else {
        None
    }
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
