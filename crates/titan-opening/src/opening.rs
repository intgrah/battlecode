//! Opening-book data model. Persisted to disk as JSON for editing
//! convenience; later exported to a `.py` file for bot consumption.
//!
//! IDs in here are *opening-local*, not engine IDs. Cores get opening
//! ID `CORE_OPENING_ID = 0` per team; builders spawned via the opening
//! get sequential IDs 1, 2, 3, … in the order their `Spawn` actions
//! fire. The editor maintains this monotone allocation; the sim layer
//! maps opening IDs to the engine IDs assigned at simulation time.
//!
//! Invariant: every unit's action vector covers turns
//! `[spawn_turn, opening.horizon)` — never past, never before.

use std::collections::HashMap;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

/// The single opening ID that every team's core uses.
pub const CORE_OPENING_ID: u32 = 0;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Opening {
    pub map_path: PathBuf,
    pub horizon: usize,
    pub teams: [TeamPlan; 2],
}

impl Opening {
    #[must_use]
    pub fn empty(map_path: PathBuf) -> Self {
        let make_core = || UnitPlan {
            spawn_turn: 0,
            actions: vec![TurnActions::default()],
        };
        let mut team_a = TeamPlan::default();
        team_a.units.insert(CORE_OPENING_ID, make_core());
        let mut team_b = TeamPlan::default();
        team_b.units.insert(CORE_OPENING_ID, make_core());
        Self {
            map_path,
            horizon: 1,
            teams: [team_a, team_b],
        }
    }

    /// Action queue for `(unit, turn)`, or empty if unscripted.
    #[must_use]
    pub fn actions(&self, team_idx: usize, opening_id: u32, turn: usize) -> &[Action] {
        let Some(plan) = self.teams[team_idx].units.get(&opening_id) else {
            return &[];
        };
        if turn < plan.spawn_turn {
            return &[];
        }
        let i = turn - plan.spawn_turn;
        plan.actions.get(i).map_or(&[][..], |t| &t.items[..])
    }

    /// Append `action` to `(unit, turn)`'s queue. Returns `false` if
    /// the unit doesn't exist yet, or `turn` is outside its lifetime.
    pub fn append_action(
        &mut self,
        team_idx: usize,
        opening_id: u32,
        turn: usize,
        action: Action,
    ) -> bool {
        let Some(plan) = self.teams[team_idx].units.get_mut(&opening_id) else {
            return false;
        };
        if turn < plan.spawn_turn {
            return false;
        }
        let i = turn - plan.spawn_turn;
        let Some(slot) = plan.actions.get_mut(i) else {
            return false;
        };
        slot.items.push(action);
        true
    }

    /// Remove the `idx`-th action from `(unit, turn)`'s queue.
    pub fn remove_action(
        &mut self,
        team_idx: usize,
        opening_id: u32,
        turn: usize,
        idx: usize,
    ) -> bool {
        let Some(plan) = self.teams[team_idx].units.get_mut(&opening_id) else {
            return false;
        };
        if turn < plan.spawn_turn {
            return false;
        }
        let i = turn - plan.spawn_turn;
        let Some(slot) = plan.actions.get_mut(i) else {
            return false;
        };
        if idx < slot.items.len() {
            slot.items.remove(idx);
            true
        } else {
            false
        }
    }

    /// Allocate the next opening ID for `team_idx`'s next-spawned
    /// builder (0 is the core; first builder is 1, etc.). Inserts a
    /// fresh `UnitPlan` whose lifetime starts at `spawn_turn` and
    /// extends to the horizon.
    pub fn allocate_builder(&mut self, team_idx: usize, spawn_turn: usize) -> u32 {
        let team = &mut self.teams[team_idx];
        // Dense from 0 (core) up; next free is `len`.
        let new_id = team.units.len() as u32;
        let n = self.horizon.saturating_sub(spawn_turn);
        team.units.insert(
            new_id,
            UnitPlan {
                spawn_turn,
                actions: vec![TurnActions::default(); n],
            },
        );
        new_id
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct TeamPlan {
    /// `opening_id` → `UnitPlan`. Dense from 0; 0 is the core.
    pub units: HashMap<u32, UnitPlan>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct UnitPlan {
    pub spawn_turn: usize,
    pub actions: Vec<TurnActions>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct TurnActions {
    pub items: Vec<Action>,
}

/// Editor-side action representation. All positions are absolute tile
/// coordinates; directions use the same encoding as `libre_engine::Direction`
/// (0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW, 8=Centre).
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
pub enum Action {
    Move { dir: i32 },
    Spawn { dir: i32 },
    BuildConveyor { x: i32, y: i32, dir: i32 },
    BuildArmouredConveyor { x: i32, y: i32, dir: i32 },
    BuildSplitter { x: i32, y: i32, dir: i32 },
    BuildBridge { x: i32, y: i32, tx: i32, ty: i32 },
    BuildHarvester { x: i32, y: i32 },
    BuildRoad { x: i32, y: i32 },
    BuildBarrier { x: i32, y: i32 },
    BuildGunner { x: i32, y: i32, dir: i32 },
    BuildSentinel { x: i32, y: i32, dir: i32 },
    BuildBreach { x: i32, y: i32, dir: i32 },
    BuildLauncher { x: i32, y: i32 },
    BuildFoundry { x: i32, y: i32 },
    Destroy { x: i32, y: i32 },
    Heal { x: i32, y: i32 },
    Attack { x: i32, y: i32 },
    PlaceMarker { x: i32, y: i32, value: u32 },
    Rotate { dir: i32 },
}

impl Action {
    /// Short label for sidebar action-queue display.
    #[must_use]
    pub fn label(&self) -> String {
        match self {
            Self::Move { dir } => format!("move {}", dir_short(*dir)),
            Self::Spawn { dir } => format!("spawn {}", dir_short(*dir)),
            Self::BuildConveyor { x, y, dir } => {
                format!("conveyor ({x},{y}) {}", dir_short(*dir))
            }
            Self::BuildArmouredConveyor { x, y, dir } => {
                format!("armoured ({x},{y}) {}", dir_short(*dir))
            }
            Self::BuildSplitter { x, y, dir } => format!("splitter ({x},{y}) {}", dir_short(*dir)),
            Self::BuildBridge { x, y, tx, ty } => format!("bridge ({x},{y})→({tx},{ty})"),
            Self::BuildHarvester { x, y } => format!("harvester ({x},{y})"),
            Self::BuildRoad { x, y } => format!("road ({x},{y})"),
            Self::BuildBarrier { x, y } => format!("barrier ({x},{y})"),
            Self::BuildGunner { x, y, dir } => format!("gunner ({x},{y}) {}", dir_short(*dir)),
            Self::BuildSentinel { x, y, dir } => format!("sentinel ({x},{y}) {}", dir_short(*dir)),
            Self::BuildBreach { x, y, dir } => format!("breach ({x},{y}) {}", dir_short(*dir)),
            Self::BuildLauncher { x, y } => format!("launcher ({x},{y})"),
            Self::BuildFoundry { x, y } => format!("foundry ({x},{y})"),
            Self::Destroy { x, y } => format!("destroy ({x},{y})"),
            Self::Heal { x, y } => format!("heal ({x},{y})"),
            Self::Attack { x, y } => format!("attack ({x},{y})"),
            Self::PlaceMarker { x, y, value } => format!("marker ({x},{y}) {value:#x}"),
            Self::Rotate { dir } => format!("rotate {}", dir_short(*dir)),
        }
    }
}

#[must_use]
const fn dir_short(d: i32) -> &'static str {
    match d {
        0 => "N",
        1 => "NE",
        2 => "E",
        3 => "SE",
        4 => "S",
        5 => "SW",
        6 => "W",
        7 => "NW",
        _ => "·",
    }
}
