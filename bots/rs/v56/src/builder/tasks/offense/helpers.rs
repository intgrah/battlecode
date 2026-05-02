//! Shared helpers for the offense task family. Hosts target-selection
//! predicates (`vulnerable_harvesters`, `pick_harvester_target`,
//! `pick_attack_destination`, `pick_conveyor_target`), gating predicates
//! (`should_attack`, `enemy_healer_near`, etc.), turret-facing math
//! (`gunner_chain_facing`), the `scout_toward_enemy` movement helper, and
//! `begin_turn_offense` — the once-per-turn state-decay prelude that runs
//! before any offense task fires.

use std::collections::HashMap;

use cambc::{
    Controller, ControllerApi, Direction, EntityType, Environment, GameConstants, Position,
};

use crate::builder::Builder;
use crate::builder::explore::explore;
use crate::builder::helpers::{can_afford, make_move, try_move_dir};
use crate::util::directions::{DIR4, DIR8};
use crate::util::metrics::{chebyshev, closest};

#[must_use]
pub fn open_tiles(self_: &Builder, positions: &[Position]) -> Vec<Position> {
    pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(positions)),
        |p| self_.is_passable(*p) && !pyrust::dict::contains!(self_.all_bots, p)
    ))
}

#[must_use]
pub fn is_allied_transport(self_: &Builder, position: Position) -> bool {
    matches!(
        self_.kind_at(position),
        Some(
            EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
                | EntityType::Bridge
        )
    ) && self_.team_at(position) == Some(self_.my_team)
}

#[must_use]
pub fn without_allied_transport(self_: &Builder, positions: &[Position]) -> Vec<Position> {
    pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(positions)),
        |&p| !is_allied_transport(self_, p)
    ))
}

#[must_use]
pub fn buildable(self_: &Builder, positions: &[Position]) -> Vec<Position> {
    pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(positions)),
        |&p| is_cheap_overbuild(self_, p)
    ))
}

fn is_cheap_overbuild(self_: &Builder, pos: Position) -> bool {
    if !self_.in_bounds(pos) {
        return false;
    }
    if self_.get_env(pos) == Some(Environment::Wall) {
        return false;
    }
    let Some(kind) = self_.kind_at(pos) else {
        return true;
    };
    if kind == EntityType::Marker {
        return true;
    }
    kind == EntityType::Road && self_.team_at(pos) == Some(self_.my_team)
}

#[must_use]
pub fn nearest_enemy_bot(self_: &Builder) -> Option<Position> {
    if pyrust::vec::is_empty!(self_.enemy_bots) {
        return None;
    }
    closest(
        self_.my_pos,
        pyrust::copied!(pyrust::iter!(self_.enemy_bots)),
    )
}

#[must_use]
pub fn should_attack(self_: &Builder, pos: Position) -> bool {
    let enemy_builder = nearest_enemy_bot(self_);
    let i = self_.idx(pos);
    pyrust::is_none!(enemy_builder)
        || chebyshev(self_.my_pos, pyrust::unwrap!(enemy_builder)) > 2
        || self_.hp[i] <= self_.max_hp[i] - 4
        || self_.hp[i] <= 4
        || can_afford(self_, EntityType::Harvester)
}

#[must_use]
pub fn enemy_healer_near(self_: &Builder, pos: Position) -> bool {
    pyrust::any!(pyrust::iter!(self_.enemy_bots), |p| p.distance_squared(pos)
        <= 2)
}

#[must_use]
pub fn friendly_bot_adjacent(self_: &Builder, pos: Position) -> bool {
    pyrust::any!(pyrust::iter!(self_.friendly_bots), |p| p
        .distance_squared(pos)
        <= 1)
}

/// Chebyshev distance from `pos` to the nearest OTHER friendly
/// builder bot.
pub fn min_friendly_chebyshev(ct: &mut Controller<'_>, pos: Position) -> i32 {
    let my_team = pyrust::unwrap!(ct.get_team(None));
    let my_id = pyrust::unwrap!(ct.get_id());
    let mut best = 999;
    for uid in pyrust::unwrap!(ct.get_nearby_units(None)) {
        if uid == my_id {
            continue;
        }
        if pyrust::unwrap!(ct.get_entity_type(Some(uid))) != EntityType::BuilderBot {
            continue;
        }
        if pyrust::unwrap!(ct.get_team(Some(uid))) != my_team {
            continue;
        }
        let d = chebyshev(pos, pyrust::unwrap!(ct.get_position(Some(uid))));
        if d < best {
            best = d;
        }
    }
    best
}

/// Pick an enemy conveyor/bridge/splitter tile to attack, falling
/// back when no harvester is vulnerable.
pub fn pick_conveyor_target(
    self_: &Builder,
    ct: &mut Controller<'_>,
    enemy_core: Position,
    my_pos: Position,
) -> Option<Position> {
    let mut best: Option<Position> = None;
    let mut best_score: Option<(i32, i32, i32)> = None;
    for &pos in &self_.nearby_buildings {
        let Some((kind, team)) = self_.get_building(pos) else {
            continue;
        };
        if team == self_.my_team {
            continue;
        }
        if !matches!(
            kind,
            EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
                | EntityType::Bridge
        ) {
            continue;
        }
        if !self_.is_passable(pos) {
            continue;
        }
        if pyrust::dict::contains!(self_.attack_tile_blacklist, &pos) {
            continue;
        }
        if pyrust::vec::contains!(self_.friendly_turret_ray_tiles, &pos) {
            continue;
        }
        if let Some(&uid) = self_.all_bots.get(&pos)
            && uid != self_.my_id
        {
            continue;
        }
        if enemy_healer_near(self_, pos) {
            continue;
        }
        let near_core = pos.distance_squared(enemy_core) <= 25;
        let mut has_flow = false;
        if pyrust::unwrap!(ct.is_in_vision(pos))
            && let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(pos))
            && pyrust::is_some!(pyrust::unwrap!(ct.get_stored_resource(Some(bid))))
        {
            has_flow = true;
        }
        let tier = if near_core {
            0
        } else if has_flow {
            1
        } else {
            continue;
        };
        let spacing = min_friendly_chebyshev(ct, pos);
        let my_dist = my_pos.distance_squared(pos);
        let score = (tier, -pyrust::min!(spacing, 3), my_dist);
        match best_score {
            Some(prev) if score >= prev => {}
            _ => {
                best = Some(pos);
                best_score = Some(score);
            }
        }
    }
    best
}

/// Pick a cardinal neighbour of `target` (an enemy harvester) for
/// us to stand on and attack.
#[must_use]
pub fn pick_attack_destination(
    self_: &Builder,
    target: Position,
    avoid_healers: bool,
) -> Option<Position> {
    let mut candidates: Vec<(i32, i32, i32, Position)> = pyrust::vec::new!();
    for d in DIR4 {
        let pos = target.add(d);
        if !self_.in_bounds(pos) {
            continue;
        }
        if !self_.is_passable(pos) {
            continue;
        }
        if is_allied_transport(self_, pos) {
            continue;
        }
        if let Some(&uid) = self_.all_bots.get(&pos)
            && uid != self_.my_id
        {
            continue;
        }
        if pyrust::dict::contains!(self_.attack_tile_blacklist, &pos) {
            continue;
        }
        if pyrust::vec::contains!(self_.friendly_turret_ray_tiles, &pos) {
            continue;
        }
        let kind = self_.kind_at(pos);
        let team = self_.team_at(pos);
        let cost = match kind {
            None => 0,
            Some(_) if team == Some(self_.my_team) => 0,
            Some(EntityType::Conveyor | EntityType::Splitter | EntityType::Bridge) => 20,
            _ => 5,
        };
        if avoid_healers && enemy_healer_near(self_, pos) {
            continue;
        }
        let in_ray: i32 = i32::from(pyrust::vec::contains!(self_.enemy_turret_ray_tiles, &pos));
        let dist = self_.my_pos.distance_squared(pos);
        pyrust::vec::push!(candidates, (in_ray, cost, dist, pos));
    }
    if pyrust::vec::is_empty!(candidates) {
        return None;
    }
    candidates.sort();
    Some(candidates[0].3)
}

/// Return a direction (any of DIR8) such that a gunner placed at
/// `pos` facing that way has an enemy conveyor/splitter/bridge as
/// the first building in its forward ray.
#[must_use]
pub fn gunner_chain_facing(self_: &Builder, pos: Position) -> Option<Direction> {
    for d in DIR8 {
        let mut current = pos;
        for _ in 0..4 {
            current = current.add(d);
            if !self_.in_bounds(current) {
                break;
            }
            if pos.distance_squared(current) > GameConstants::GUNNER_VISION_RADIUS_SQ {
                break;
            }
            if self_.get_env(current) == Some(Environment::Wall) {
                break;
            }
            let Some((kind, team)) = self_.get_building(current) else {
                continue;
            };
            if team == self_.my_team {
                break;
            }
            if matches!(
                kind,
                EntityType::Conveyor
                    | EntityType::ArmouredConveyor
                    | EntityType::Splitter
                    | EntityType::Bridge
            ) {
                return Some(d);
            }
            break;
        }
    }
    None
}

/// True iff `position` has at least one passable, unoccupied,
/// non-allied-transport cardinal neighbour.
fn has_open_side(self_: &Builder, position: Position) -> bool {
    for direction in DIR4 {
        let new_position = position.add(direction);
        if !self_.in_bounds(new_position) {
            continue;
        }
        let occupied = match self_.all_bots.get(&new_position) {
            Some(&uid) if uid != self_.my_id => true,
            _ => false,
        };
        if self_.is_passable(new_position) && !occupied && !is_allied_transport(self_, new_position)
        {
            return true;
        }
    }
    false
}

/// Enemy harvesters with at least one passable, unoccupied,
/// non-allied-transport cardinal.
#[must_use]
pub fn vulnerable_harvesters(self_: &Builder) -> Vec<Position> {
    let mut result: Vec<Position> = pyrust::vec::new!();
    for &p in &self_.nearby_buildings {
        let Some((kind, team)) = self_.get_building(p) else {
            continue;
        };
        if team == self_.my_team {
            continue;
        }
        if kind != EntityType::Harvester {
            continue;
        }
        if has_open_side(self_, p) {
            pyrust::vec::push!(result, p);
        }
    }
    result
}

/// 3-tier preference over vulnerable harvesters.
#[must_use]
pub fn pick_harvester_target(self_: &Builder, vulnerable: &[Position]) -> Position {
    let my_pos = self_.my_pos;
    let mut sorted: Vec<Position> = pyrust::to_vec!(vulnerable);
    pyrust::sort_by_key!(sorted, |p| my_pos.distance_squared(*p));
    for &h in &sorted {
        if !enemy_healer_near(self_, h) && !friendly_bot_adjacent(self_, h) {
            return h;
        }
    }
    for &h in &sorted {
        if !enemy_healer_near(self_, h) {
            return h;
        }
    }
    pyrust::expect!(
        closest(my_pos, pyrust::copied!(pyrust::iter!(vulnerable))),
        "vulnerable is non-empty by caller contract"
    )
}

pub fn scout_toward_enemy(self_: &mut Builder, ct: &mut Controller<'_>) {
    let en_core = self_.en_core_guess;

    if pyrust::vec::contains!(self_.nearby_tiles, &en_core) {
        self_.en_core_seen = true;
    }

    if !self_.en_core_seen {
        make_move(self_, ct, en_core);
    } else if pyrust::vec::contains!(self_.nearby_tiles, &en_core)
        || self_.ti
            >= (pyrust::float!(GameConstants::HARVESTER_BASE_COST.0 + 50) * (1.0 + self_.scale))
                as i32
    {
        explore(self_, ct);
    } else {
        let mut dir8 = pyrust::to_vec!(DIR8);
        self_.rng.shuffle(&mut dir8);
        for d in dir8 {
            if try_move_dir(ct, d) {
                break;
            }
        }
    }
}

/// Per-turn offense bookkeeping.
pub fn begin_turn_offense(self_: &mut Builder, ct: &mut Controller<'_>) {
    if !pyrust::vec::is_empty!(self_.attack_tile_blacklist) {
        let new_blacklist: HashMap<Position, i32> = pyrust::dict::collect!(pyrust::filter_map!(
            pyrust::dict::items!(self_.attack_tile_blacklist),
            |t| if *t.1 > 1 {
                Some((*t.0, *t.1 - 1))
            } else {
                None
            }
        ));
        self_.attack_tile_blacklist = new_blacklist;
    }
    if let Some(last) = self_.last_fire
        && self_.my_pos != last.0
    {
        self_.last_fire = None;
    }

    let mut invalidate_target = false;
    if self_.offense_turns > 25 {
        invalidate_target = true;
    } else if let Some(tgt) = self_.offense_target
        && pyrust::unwrap!(ct.is_in_vision(tgt))
    {
        let occupied = match self_.all_bots.get(&tgt) {
            Some(&uid) if uid != self_.my_id => true,
            _ => false,
        };
        invalidate_target = !self_.is_enemy_building(tgt) || !self_.is_passable(tgt) || occupied;
    }

    if invalidate_target {
        self_.offense_target = None;
        self_.offense_launcher = None;
        self_.offense_turns = 0;
    } else {
        self_.offense_turns += 1;
    }
}
