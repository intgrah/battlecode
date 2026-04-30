//! Translation of `bots/intgrah/v54.7.9/launcher/__init__.py`.

use cambc::{Controller, ControllerApi, EntityType, Environment, GameConstants, Position};

use crate::unit::{Unit, UnitState, run_default};
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
    fn is_empty_walkable(&self, ct: &mut Controller<'_>, pos: Position) -> bool {
        self.is_walkable(ct, pos) && !self.state.all_bots.contains_key(&pos)
    }

    fn is_walkable(&self, ct: &mut Controller<'_>, pos: Position) -> bool {
        if !self.in_bounds(pos) || !ct.is_in_vision(pos).unwrap() {
            return false;
        }
        if ct.get_tile_env(pos).unwrap() == Environment::Wall {
            return false;
        }
        let Some(bid) = ct.get_tile_building_id(pos).unwrap() else {
            return false;
        };
        let et = ct.get_entity_type(Some(bid)).unwrap();
        PASSABLE_BUILDINGS.contains(&et)
    }

    fn find_harvester_attack_tiles(&self, ct: &mut Controller<'_>) -> Vec<Position> {
        let mut targets: Vec<Position> = Vec::new();
        let nearby = self.state.nearby_tiles.clone();
        let my_team = self.state.my_team;
        for pos in nearby {
            let Some(bid) = ct.get_tile_building_id(pos).unwrap() else {
                continue;
            };
            if ct.get_entity_type(Some(bid)).unwrap() != EntityType::Harvester {
                continue;
            }
            if ct.get_team(Some(bid)).unwrap() == my_team {
                continue;
            }
            for &d in &DIR4 {
                let adj = pos.add(d);
                if !self.is_empty_walkable(ct, adj) {
                    continue;
                }
                let Some(adj_bid) = ct.get_tile_building_id(adj).unwrap() else {
                    continue;
                };
                if ct.get_team(Some(adj_bid)).unwrap() == my_team {
                    continue;
                }
                targets.push(adj);
            }
        }
        targets
    }

    fn find_enemy_throw_tile(&self, ct: &mut Controller<'_>) -> (Option<Position>, i32) {
        let mut best: Option<Position> = None;
        let mut best_dist: i32 = 0;
        let nearby = self.state.nearby_tiles.clone();
        let my_team = self.state.my_team;
        let my_pos = self.state.my_pos;
        for pos in nearby {
            let bid = ct.get_tile_building_id(pos).unwrap();
            if !self.is_empty_walkable(ct, pos) {
                continue;
            }
            if let Some(b) = bid
                && ct.get_team(Some(b)).unwrap() == my_team
            {
                continue;
            }
            let dist = my_pos.distance_squared(pos);
            if dist > best_dist {
                best_dist = dist;
                best = Some(pos);
            }
        }
        (best, best_dist)
    }
}

impl Unit for Launcher {
    fn state(&self) -> &UnitState {
        &self.state
    }

    fn state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        run_default(self, ct);

        let (enemy_throw_tile, enemy_throw_dist) = self.find_enemy_throw_tile(ct);
        let harvester_targets = self.find_harvester_attack_tiles(ct);
        let harvest_dest: Option<Position> = harvester_targets.first().copied();

        let mut best_bot: Option<Position> = None;
        let mut best_dest: Option<Position> = None;
        let mut best_score: i32 = 0;

        let my_team = self.state.my_team;
        for uid in ct
            .get_nearby_units(Some(GameConstants::ACTION_RADIUS_SQ))
            .unwrap()
        {
            if ct.get_entity_type(Some(uid)).unwrap() != EntityType::BuilderBot {
                continue;
            }

            let mut score: i32 = 0;
            let mut dest: Option<Position> = None;

            let team = ct.get_team(Some(uid)).unwrap();
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
                best_bot = Some(ct.get_position(Some(uid)).unwrap());
                best_dest = dest;
                best_score = score;
            }
        }

        if let Some(bb) = best_bot
            && let Some(bd) = best_dest
            && ct.can_launch(bb, bd).unwrap()
        {
            ct.launch(bb, bd).unwrap();
        }
    }
}
