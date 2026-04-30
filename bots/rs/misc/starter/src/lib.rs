//! Starter bot - simple example with a self-contained deterministic PRNG.
//!
//! Each unit gets its own Player instance; the engine calls run() once per round.
//! Use Controller.get_entity_type() to branch on what kind of unit you are.
//!
//! This bot:
//!   - Core: spawns up to 3 builder bots on random adjacent tiles
//!   - Builder bot: builds a harvester on any adjacent ore tile, then moves in a
//!     random direction (laying a road first so the tile is passable), and places
//!     a marker recording the current round number
//!
//! RNG: a Numerical-Recipes LCG (state' = state*1664525 + 1013904223 mod 2^32),
//! seeded from the unit's id on the first run() call. Deterministic across
//! native-Rust and pyrust-translated runs at the same map+seed.

use cambc::*;

const DIRECTIONS_ALL: [Direction; 9] = [
    Direction::North,
    Direction::Northeast,
    Direction::East,
    Direction::Southeast,
    Direction::South,
    Direction::Southwest,
    Direction::West,
    Direction::Northwest,
    Direction::Centre,
];

const DIRECTIONS: [Direction; 8] = [
    Direction::North,
    Direction::Northeast,
    Direction::East,
    Direction::Southeast,
    Direction::South,
    Direction::Southwest,
    Direction::West,
    Direction::Northwest,
];

pub struct Player {
    num_spawned: i32,
    state: i64,
}

impl Player {
    pub fn new() -> Self {
        Self {
            num_spawned: 0,
            state: 0,
        }
    }

    fn next_rand(&mut self) -> i64 {
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF;
        self.state
    }
}

impl Default for Player {
    fn default() -> Self {
        Self::new()
    }
}

impl Bot for Player {
    fn run(&mut self, ct: &mut Controller<'_>) {
        if self.state == 0 {
            self.state = ct.get_id().unwrap() as i64;
        }
        let etype = ct.get_entity_type(None).unwrap();
        if etype == EntityType::Core {
            if self.num_spawned < 3 {
                let idx = self.next_rand() % 8;
                let spawn_pos = ct
                    .get_position(None)
                    .unwrap()
                    .add(DIRECTIONS[idx as usize]);
                if ct.can_spawn(spawn_pos).unwrap() {
                    ct.spawn_builder(spawn_pos).ok();
                    self.num_spawned += 1;
                }
            }
        } else if etype == EntityType::BuilderBot {
            for d in DIRECTIONS_ALL {
                let check_pos = ct.get_position(None).unwrap().add(d);
                if ct.can_build_harvester(check_pos).unwrap() {
                    ct.build_harvester(check_pos).ok();
                    break;
                }
            }

            let move_dir = DIRECTIONS[(self.next_rand() % 8) as usize];
            let move_pos = ct.get_position(None).unwrap().add(move_dir);
            if ct.can_build_road(move_pos).unwrap() {
                ct.build_road(move_pos).ok();
            }
            if ct.can_move(move_dir).unwrap() {
                ct.move_(move_dir).ok();
            }

            let marker_pos = ct
                .get_position(None)
                .unwrap()
                .add(DIRECTIONS[(self.next_rand() % 8) as usize]);
            if ct.can_place_marker(marker_pos).unwrap() {
                ct.place_marker(marker_pos, ct.get_current_round().unwrap() as u32)
                    .ok();
            }
        }
    }
}

cambc_bot!(Player);
