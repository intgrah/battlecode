//! Translation of `bots/intgrah/v54.7.9/sentinel/__init__.py`.

use cambc::{Controller, ControllerApi, Direction, EntityType, GameConstants, Position, Team};

use crate::unit::{Unit, UnitState};

const SELF_DESTRUCT_THRESHOLD: i32 = 16;

const fn is_enemy_combat(et: EntityType) -> bool {
    matches!(
        et,
        EntityType::Core
            | EntityType::Breach
            | EntityType::Sentinel
            | EntityType::Gunner
            | EntityType::Launcher,
    )
}

const fn is_transport(et: EntityType) -> bool {
    matches!(
        et,
        EntityType::Conveyor
            | EntityType::ArmouredConveyor
            | EntityType::Splitter
            | EntityType::Bridge,
    )
}

const fn priority(et: EntityType) -> i32 {
    match et {
        EntityType::Splitter => 9,
        EntityType::Bridge => 8,
        EntityType::Breach => 7,
        EntityType::Sentinel => 6,
        EntityType::Gunner => 5,
        EntityType::Launcher => 4,
        EntityType::Conveyor | EntityType::ArmouredConveyor => 3,
        EntityType::Core | EntityType::Foundry => 2,
        EntityType::Barrier | EntityType::Road => 1,
        _ => 0,
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

const fn rotate_left(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::Northwest,
        Direction::Northeast => Direction::North,
        Direction::East => Direction::Northeast,
        Direction::Southeast => Direction::East,
        Direction::South => Direction::Southeast,
        Direction::Southwest => Direction::South,
        Direction::West => Direction::Southwest,
        Direction::Northwest => Direction::West,
        Direction::Centre => Direction::Centre,
    }
}

const fn _builder_score(hp: i32) -> i32 {
    if hp <= GameConstants::SENTINEL_DAMAGE {
        return 15;
    }
    if hp < GameConstants::BUILDER_BOT_MAX_HP {
        return 7;
    }
    5
}

fn _transport_outputs(
    ct: &mut Controller<'_>,
    bid: i32,
    pos: Position,
    etype: EntityType,
) -> Vec<Position> {
    if etype == EntityType::Bridge {
        return vec![pyrust::unwrap!(ct.get_bridge_target(bid))];
    }
    let d = pyrust::unwrap!(ct.get_direction(Some(bid)));
    if etype == EntityType::Splitter {
        return vec![
            pos.add(d),
            pos.add(rotate_right(rotate_right(d))),
            pos.add(rotate_left(rotate_left(d))),
        ];
    }
    vec![pos.add(d)]
}

fn _feeds_enemy_combat(ct: &mut Controller<'_>, my_team: Team, outputs: &[Position]) -> bool {
    for &out in outputs {
        if !pyrust::unwrap!(ct.is_in_vision(out)) {
            continue;
        }
        let Some(out_bid) = pyrust::unwrap!(ct.get_tile_building_id(out)) else {
            continue;
        };
        if pyrust::unwrap!(ct.get_team(Some(out_bid))) == my_team {
            continue;
        }
        if is_enemy_combat(pyrust::unwrap!(ct.get_entity_type(Some(out_bid)))) {
            return true;
        }
    }
    false
}

#[derive(Default)]
pub struct Sentinel {
    state: UnitState,
    idle_turns: i32,
}

impl Sentinel {
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: UnitState::new(),
            idle_turns: 0,
        }
    }

    fn try_self_destruct(&mut self, ct: &mut Controller<'_>) {
        let my_team = self.state.my_team;
        let mut has_ally = false;
        for uid in pyrust::unwrap!(ct.get_nearby_units(None)) {
            if pyrust::unwrap!(ct.get_team(Some(uid))) == my_team {
                has_ally = true;
            } else {
                return;
            }
        }
        if has_ally {
            pyrust::unwrap!(ct.self_destruct());
        }
    }
}

impl Unit for Sentinel {
    fn unit_state(&self) -> &UnitState {
        &self.state
    }

    fn unit_state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);
        if pyrust::unwrap!(ct.get_action_cooldown()) > 0 {
            return;
        }

        let my_team = self.state.my_team;
        let mut best_score: i32 = -1;
        let mut best_target: Option<Position> = None;

        let attackable = pyrust::unwrap!(ct.get_attackable_tiles());
        for tile in attackable {
            let bid = pyrust::unwrap!(ct.get_tile_building_id(tile));
            let uid = pyrust::copied!(self.state.all_bots.get(&tile));

            if pyrust::vec::contains!(self.state.enemy_bots, &tile) {
                let hp = pyrust::unwrap!(ct.get_hp(uid));
                let score = _builder_score(hp);
                if score > best_score {
                    best_score = score;
                    best_target = Some(tile);
                }
                continue;
            }

            if pyrust::vec::contains!(self.state.friendly_bots, &tile) {
                continue;
            }

            let Some(bid) = bid else {
                continue;
            };
            if pyrust::unwrap!(ct.get_team(Some(bid))) == my_team {
                continue;
            }
            let etype = pyrust::unwrap!(ct.get_entity_type(Some(bid)));
            if matches!(etype, EntityType::Marker | EntityType::Harvester) {
                continue;
            }
            let mut score = priority(etype);
            if is_transport(etype) {
                let outputs = _transport_outputs(ct, bid, tile, etype);
                if _feeds_enemy_combat(ct, my_team, &outputs) {
                    score = 12;
                }
            }
            if pyrust::unwrap!(ct.get_hp(Some(bid))) <= GameConstants::SENTINEL_DAMAGE {
                score += 1;
            }
            if score > best_score {
                best_score = score;
                best_target = Some(tile);
            }
        }

        if let Some(target) = best_target
            && pyrust::unwrap!(ct.can_fire(target))
        {
            pyrust::unwrap!(ct.fire(target));
            self.idle_turns = 0;
        } else {
            self.idle_turns += 1;
            if self.idle_turns > SELF_DESTRUCT_THRESHOLD {
                self.try_self_destruct(ct);
            }
        }
    }
}
