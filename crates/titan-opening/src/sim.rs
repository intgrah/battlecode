//! Engine-driven simulator for the opening editor. Wraps `libre_engine::Game`
//! and feeds it scripted actions through `UnitView` (the engine's bot-side
//! `Controller`). Resimulates from turn 0 on every edit — short openings
//! make this trivial.

use std::collections::HashMap;
use std::path::Path;

use libre_engine::common::{Direction, Pos, Team};
use libre_engine::controller::{Controller, UnitView};
use libre_engine::game::Game;
use libre_engine::game_map::Entity;

use crate::opening::{Action, Opening};

/// "During turn `turn`, after `unit_idx` units have already acted." When
/// `unit_idx == turn_units.len()` the cursor is at end-of-turn (post-
/// distribute, post-cooldowns); the next step rolls into turn+1.
#[derive(Clone, Copy, Debug)]
pub struct Cursor {
    pub turn: usize,
    pub unit_idx: usize,
}

pub struct Sim {
    pub game: Game,
    /// Snapshot of `game.unit_order` taken at start-of-turn, frozen so
    /// `unit_idx` indexes deterministically into it for the whole turn.
    pub turn_units: Vec<i32>,
    pub cursor: Cursor,
    /// `engine_id → opening_id` for player-team units only. Team B
    /// entities are never registered — the opening doesn't model them
    /// and `dispatch_unit` short-circuits on missing keys.
    /// The player-team core is inserted at `from_map` time; children
    /// (builders, turrets, launchers) bind to their pre-allocated
    /// `UnitPlan` ids when their creating action fires.
    pub engine_to_opening: HashMap<i32, u32>,
    /// `opening_id → (birth_turn, birth_x, birth_y)`. This is the
    /// runtime-stable identity used by the exported Python: engine
    /// ids interleave between teams in the real game and don't match
    /// what we see locally, but a unit's birthday turn and birth
    /// tile uniquely pin it down.
    pub birth: HashMap<u32, (usize, i32, i32)>,
}

impl Sim {
    pub fn from_map(map_path: &Path) -> Result<Self, String> {
        let path_str = map_path
            .to_str()
            .ok_or_else(|| "non-UTF8 map path".to_string())?;
        let (env, cores) =
            libre_replay::map_loader::load_map(path_str).map_err(|e| format!("load map: {e}"))?;
        let game = Game::new(env, cores, 0, true);
        let turn_units = game.unit_order.clone();

        // Player team A only. Team B's core exists on the map for
        // symmetry but isn't tracked — `advance_unit` skips any
        // engine_id that's not in this map.
        let mut engine_to_opening = HashMap::new();
        let mut birth = HashMap::new();
        for (&id, e) in &game.entities {
            if matches!(e, Entity::Core(_)) && matches!(e.team, Team::A) {
                engine_to_opening.insert(id, crate::opening::CORE_OPENING_ID);
                birth.insert(
                    crate::opening::CORE_OPENING_ID,
                    (0_usize, e.position.x, e.position.y),
                );
            }
        }

        Ok(Self {
            game,
            turn_units,
            cursor: Cursor {
                turn: 0,
                unit_idx: 0,
            },
            engine_to_opening,
            birth,
        })
    }

    /// Resimulate from turn 0 to the given cursor. `target.unit_idx`
    /// is clamped to the turn's actual unit count, so callers can pass
    /// `usize::MAX` to mean "end of this turn's units".
    pub fn seek(&mut self, opening: &Opening, target: Cursor) -> Result<(), Vec<SimError>> {
        let path = opening.map_path.clone();
        match Self::from_map(&path) {
            Ok(fresh) => *self = fresh,
            Err(e) => return Err(vec![SimError::Other(e)]),
        }
        let mut errors: Vec<SimError> = Vec::new();
        for _ in 0..target.turn {
            errors.extend(self.advance_turn(opening));
        }
        if target.unit_idx > 0 {
            // start_of_turn populates `turn_units` so we can clamp.
            self.start_of_turn();
            let cap = self.turn_units.len();
            let want = target.unit_idx.min(cap);
            for _ in 0..want {
                if let Err(e) = self.advance_unit(opening) {
                    errors.extend(e);
                }
            }
        }
        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }

    /// Step one unit's worth of scripted actions, or end-of-turn if
    /// we're at the last unit of the turn.
    pub fn step_unit(&mut self, opening: &Opening) -> Result<(), Vec<SimError>> {
        if self.cursor.unit_idx >= self.turn_units.len() {
            self.end_of_turn();
            Ok(())
        } else {
            self.advance_unit(opening)
        }
    }

    /// Advance a full turn: all remaining units, then end-of-turn.
    pub fn step_turn(&mut self, opening: &Opening) -> Vec<SimError> {
        self.advance_turn(opening)
    }

    fn advance_turn(&mut self, opening: &Opening) -> Vec<SimError> {
        let mut errors: Vec<SimError> = Vec::new();
        if self.cursor.unit_idx == 0 {
            self.start_of_turn();
        }
        while self.cursor.unit_idx < self.turn_units.len() {
            if let Err(mut e) = self.advance_unit(opening) {
                errors.append(&mut e);
            }
        }
        self.end_of_turn();
        errors
    }

    fn start_of_turn(&mut self) {
        self.game.new_turn();
        self.turn_units = self.game.unit_order.clone();
    }

    fn end_of_turn(&mut self) {
        self.game.distribute_resources();
        self.game.update_cooldowns();
        const PASSIVE_INTERVAL: i32 =
            libre_engine::common::game_constants::PASSIVE_TITANIUM_INTERVAL;
        const PASSIVE_AMOUNT: i32 = libre_engine::common::game_constants::PASSIVE_TITANIUM_AMOUNT;
        if (self.game.turn + 1) % PASSIVE_INTERVAL == 0 {
            for p in &mut self.game.players {
                p.titanium += PASSIVE_AMOUNT;
            }
        }
        self.game.turn += 1;
        self.cursor.turn += 1;
        self.cursor.unit_idx = 0;
    }

    fn advance_unit(&mut self, opening: &Opening) -> Result<(), Vec<SimError>> {
        if self.cursor.unit_idx == 0 {
            self.start_of_turn();
        }
        let Some(&uid) = self.turn_units.get(self.cursor.unit_idx) else {
            self.cursor.unit_idx += 1;
            return Ok(());
        };

        let Some(&opening_id) = self.engine_to_opening.get(&uid) else {
            // Untracked entity (team B core, mid-turn ghost, etc.).
            // The opening doesn't model it; skip its action slot.
            self.cursor.unit_idx += 1;
            return Ok(());
        };

        let actions: Vec<Action> = opening.actions(opening_id, self.cursor.turn).to_vec();

        let mut errors: Vec<SimError> = Vec::new();
        for action in actions {
            let creates = action.creates_unit().is_some();
            match dispatch_one(&mut self.game, uid, action) {
                Ok(Some(new_id)) if creates => {
                    // Bind the new entity to the pre-allocated UnitPlan
                    // whose (parent, spawn_turn) matches. The plan was
                    // allocated by `Opening::ensure_unit_tree` when
                    // the user added the creating action.
                    let child_spawn = self.cursor.turn + 1;
                    let child_opening_id = opening
                        .team
                        .units
                        .iter()
                        .find(|(_, p)| p.parent == Some(opening_id) && p.spawn_turn == child_spawn)
                        .map(|(&id, _)| id);
                    if let Some(cid) = child_opening_id {
                        self.engine_to_opening.insert(new_id, cid);
                        // Capture birth tile from the new entity's
                        // current position. The engine places newly
                        // built turrets / spawned builders on the
                        // requested tile, so this is the unit's
                        // birthday position — what the runtime bot
                        // will see on its first `run()`.
                        if let Some(e) = self.game.entities.get(&new_id) {
                            self.birth
                                .insert(cid, (child_spawn, e.position.x, e.position.y));
                        }
                    }
                }
                Ok(_) => {}
                Err(message) => errors.push(SimError::Action {
                    turn: self.cursor.turn,
                    unit_id: uid,
                    message,
                }),
            }
        }
        self.cursor.unit_idx += 1;
        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }
}

#[derive(Debug, Clone)]
pub enum SimError {
    Action {
        turn: usize,
        unit_id: i32,
        message: String,
    },
    Other(String),
}

/// Returns the engine ID of any newly-created entity (`Some` for spawn /
/// build actions; `None` for moves / destroys / etc.).
fn dispatch_one(game: &mut Game, uid: i32, action: Action) -> Result<Option<i32>, String> {
    let mut view = UnitView::new(game, uid);
    match action {
        Action::Move { dir } => view.move_(direction(dir)?).map(|()| None).map_err(stringify),

        Action::Spawn { dir } => {
            let centre = view.get_position(None).map_err(stringify)?;
            let (dx, dy) = direction(dir)?.delta();
            let target = Pos {
                x: centre.x + dx,
                y: centre.y + dy,
            };
            view.spawn_builder(target).map(Some).map_err(stringify)
        }

        Action::BuildConveyor { x, y, dir } => view
            .build_conveyor(Pos { x, y }, direction(dir)?)
            .map(Some)
            .map_err(stringify),
        Action::BuildArmouredConveyor { x, y, dir } => view
            .build_armoured_conveyor(Pos { x, y }, direction(dir)?)
            .map(Some)
            .map_err(stringify),
        Action::BuildSplitter { x, y, dir } => view
            .build_splitter(Pos { x, y }, direction(dir)?)
            .map(Some)
            .map_err(stringify),
        Action::BuildBridge { x, y, tx, ty } => view
            .build_bridge(Pos { x, y }, Pos { x: tx, y: ty })
            .map(Some)
            .map_err(stringify),
        Action::BuildHarvester { x, y } => view
            .build_harvester(Pos { x, y })
            .map(Some)
            .map_err(stringify),
        Action::BuildRoad { x, y } => view.build_road(Pos { x, y }).map(Some).map_err(stringify),
        Action::BuildBarrier { x, y } => view
            .build_barrier(Pos { x, y })
            .map(Some)
            .map_err(stringify),
        Action::BuildGunner { x, y, dir } => view
            .build_gunner(Pos { x, y }, direction(dir)?)
            .map(Some)
            .map_err(stringify),
        Action::BuildSentinel { x, y, dir } => view
            .build_sentinel(Pos { x, y }, direction(dir)?)
            .map(Some)
            .map_err(stringify),
        Action::BuildBreach { x, y, dir } => view
            .build_breach(Pos { x, y }, direction(dir)?)
            .map(Some)
            .map_err(stringify),
        Action::BuildLauncher { x, y } => view
            .build_launcher(Pos { x, y })
            .map(Some)
            .map_err(stringify),
        Action::BuildFoundry { x, y } => view
            .build_foundry(Pos { x, y })
            .map(Some)
            .map_err(stringify),

        Action::Destroy { x, y } => view.destroy(Pos { x, y }).map(|()| None).map_err(stringify),
        Action::Heal { x, y } => view.heal(Pos { x, y }).map(|()| None).map_err(stringify),
        Action::Attack { x, y } => view.fire(Pos { x, y }).map(|()| None).map_err(stringify),
        Action::PlaceMarker { x, y, value } => view
            .place_marker(Pos { x, y }, value)
            .map(|()| None)
            .map_err(stringify),
        Action::Rotate { dir } => view
            .rotate(direction(dir)?)
            .map(|()| None)
            .map_err(stringify),
    }
}

const fn direction(v: i32) -> Result<Direction, String> {
    Ok(match v {
        0 => Direction::North,
        1 => Direction::Northeast,
        2 => Direction::East,
        3 => Direction::Southeast,
        4 => Direction::South,
        5 => Direction::Southwest,
        6 => Direction::West,
        7 => Direction::Northwest,
        8 => Direction::Centre,
        _ => return Err(String::new()),
    })
}

fn stringify<E: std::fmt::Display>(e: E) -> String {
    e.to_string()
}
