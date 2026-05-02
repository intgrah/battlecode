//! Translation of `bots/intgrah/v54.7.9/launcher/__init__.py`.
//!
//! Phase 5 PosInt note: Launcher uses UnitState (not Builder). The hot loop in
//! find_harvester_attack_tiles iterates nearby_tiles (Vec<Position>) and calls
//! ct API on each — no per-tile Builder array access possible.
//! TODO Phase 5 holdout: convert when UnitState gains _p accessors.

use cambc::{Controller, ControllerApi, EntityType, Environment, GameConstants, Position};

use crate::unit::{Unit, UnitState};
use crate::util::directions::DIR4;

const PASSABLE_BUILDINGS: [EntityType; 5] = [
    EntityType::Conveyor,
    EntityType::Road,
    EntityType::Splitter,
    EntityType::ArmouredConveyor,
    EntityType::Bridge,
];

#[derive(Default)]
pub struct Launcher {
    state: UnitState,
}

impl Launcher {
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: UnitState::new(),
        }
    }

    fn is_empty_walkable(&self, ct: &mut Controller<'_>, pos: Position) -> bool {
        self.is_walkable(ct, pos) && !pyrust::dict::contains!(self.state.all_bots, &pos)
    }

    fn is_walkable(&self, ct: &mut Controller<'_>, pos: Position) -> bool {
        if !self.in_bounds(pos) || !pyrust::unwrap!(ct.is_in_vision(pos)) {
            return false;
        }
        if pyrust::unwrap!(ct.get_tile_env(pos)) == Environment::Wall {
            return false;
        }
        let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(pos)) else {
            return false;
        };
        let et = pyrust::unwrap!(ct.get_entity_type(Some(bid)));
        pyrust::vec::contains!(PASSABLE_BUILDINGS, &et)
    }

    fn find_harvester_attack_tiles(&self, ct: &mut Controller<'_>) -> Vec<Position> {
        let mut targets: Vec<Position> = pyrust::vec::new!();
        let nearby = pyrust::clone!(self.state.nearby_tiles);
        let my_team = self.state.my_team;
        for pos in nearby {
            let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(pos)) else {
                continue;
            };
            if pyrust::unwrap!(ct.get_entity_type(Some(bid))) != EntityType::Harvester {
                continue;
            }
            if pyrust::unwrap!(ct.get_team(Some(bid))) == my_team {
                continue;
            }
            for &d in &DIR4 {
                let adj = pos.add(d);
                if !self.is_empty_walkable(ct, adj) {
                    continue;
                }
                let Some(adj_bid) = pyrust::unwrap!(ct.get_tile_building_id(adj)) else {
                    continue;
                };
                if pyrust::unwrap!(ct.get_team(Some(adj_bid))) == my_team {
                    continue;
                }
                pyrust::vec::push!(targets, adj);
            }
        }
        targets
    }

    fn find_enemy_throw_tile(&self, ct: &mut Controller<'_>) -> (Option<Position>, i32) {
        // Throw enemies AWAY from their econ. Proxy for "away from
        // enemy core" without needing the core position: sum of
        // distance² from each visible enemy building (conveyor, etc).
        // The chosen tile maximizes that sum — i.e. is farthest from
        // their infrastructure. Falls back to "farthest from us" if no
        // enemy buildings are visible.
        let nearby = pyrust::clone!(self.state.nearby_tiles);
        let my_team = self.state.my_team;
        let my_pos = self.state.my_pos;
        // Collect visible enemy building positions.
        let mut enemy_buildings: Vec<Position> = pyrust::vec::new!();
        for &p in &nearby {
            let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(p)) else {
                continue;
            };
            if pyrust::unwrap!(ct.get_team(Some(bid))) != my_team {
                pyrust::vec::push!(enemy_buildings, p);
            }
        }
        let mut best: Option<Position> = None;
        let mut best_score: i64 = i64::MIN;
        for pos in nearby {
            if !self.is_empty_walkable(ct, pos) {
                continue;
            }
            let bid = pyrust::unwrap!(ct.get_tile_building_id(pos));
            if let Some(b) = bid
                && pyrust::unwrap!(ct.get_team(Some(b))) == my_team
            {
                continue;
            }
            let mut score: i64;
            if pyrust::vec::is_empty!(enemy_buildings) {
                score = my_pos.distance_squared(pos) as i64;
            } else {
                score = 0;
                for ep in &enemy_buildings {
                    score += pos.distance_squared(*ep) as i64;
                }
            }
            if score > best_score {
                best_score = score;
                best = Some(pos);
            }
        }
        // Caller wants throw-distance for priority comparison vs the
        // friendly-throw branch.
        let dist = match best {
            Some(p) => my_pos.distance_squared(p),
            None => 0,
        };
        (best, dist)
    }
}

impl Unit for Launcher {
    fn unit_state(&self) -> &UnitState {
        &self.state
    }

    fn unit_state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);

        let (enemy_throw_tile, enemy_throw_dist) = self.find_enemy_throw_tile(ct);
        let harvester_targets = self.find_harvester_attack_tiles(ct);
        let harvest_dest: Option<Position> = if pyrust::vec::is_empty!(harvester_targets) {
            None
        } else {
            Some(harvester_targets[0])
        };

        let mut best_bot: Option<Position> = None;
        let mut best_dest: Option<Position> = None;
        let mut best_score: i32 = 0;

        let my_team = self.state.my_team;
        for uid in pyrust::unwrap!(ct.get_nearby_units(Some(GameConstants::ACTION_RADIUS_SQ))) {
            if pyrust::unwrap!(ct.get_entity_type(Some(uid))) != EntityType::BuilderBot {
                continue;
            }

            let mut score: i32 = 0;
            let mut dest: Option<Position> = None;

            let team = pyrust::unwrap!(ct.get_team(Some(uid)));
            if team == my_team {
                if let Some(hd) = harvest_dest {
                    score = 8;
                    dest = Some(hd);
                }
            } else if let Some(et) = enemy_throw_tile {
                score = enemy_throw_dist;
                dest = Some(et);
            }

            if score > best_score {
                best_bot = Some(pyrust::unwrap!(ct.get_position(Some(uid))));
                best_dest = dest;
                best_score = score;
            }
        }

        if let Some(bb) = best_bot
            && let Some(bd) = best_dest
            && pyrust::unwrap!(ct.can_launch(bb, bd))
        {
            pyrust::unwrap!(ct.launch(bb, bd));
        }
    }
}
