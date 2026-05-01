//! Opening-book data model. Persisted to disk as JSON; later baked
//! into a self-contained Python file the bot imports.
//!
//! An opening describes a single player's plan. Team B is *not*
//! represented anywhere in the file: the editor authors only one
//! player's plan, and the runtime mirrors coordinates if our bot is
//! loaded as team B. The map's two cores and the engine's two-team
//! starting state are properties of the runtime environment, not of
//! the plan.
//!
//! Units form a spawn tree:
//! - `CORE_OPENING_ID = 0` is the root.
//! - Each `Spawn` action produces a builder.
//! - Each `BuildGunner` / `BuildSentinel` / `BuildBreach` /
//!   `BuildLauncher` action produces a turret (or launcher) with its
//!   own per-turn action plan.
//! Passive structures (conveyors, splitters, bridges, harvesters,
//! foundries, roads, barriers, markers) don't get plans — the engine
//! handles them automatically.
//!
//! Invariant: every unit's action vector covers turns
//! `[spawn_turn, opening.horizon)`.

use std::collections::HashMap;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

/// Opening ID of the root core. All other unit plans get IDs from
/// `Opening.next_id`, allocated sparsely so removed branches don't
/// renumber surviving siblings.
pub const CORE_OPENING_ID: u32 = 0;

/// Default horizon for a fresh opening. Covers a typical opening
/// phase without forcing the user to bump it manually before things
/// work.
pub const DEFAULT_HORIZON: usize = 30;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Opening {
    pub map_path: PathBuf,
    pub horizon: usize,
    pub team: TeamPlan,
    /// Monotone id allocator. Removed children leave gaps; new
    /// allocations always pick `next_id` then bump it. Keeps tree
    /// node identity stable across edits.
    #[serde(default)]
    pub next_id: u32,
}

impl Opening {
    #[must_use]
    pub fn empty(map_path: PathBuf) -> Self {
        let mut team = TeamPlan::default();
        team.units.insert(
            CORE_OPENING_ID,
            UnitPlan {
                kind: UnitKind::Core,
                parent: None,
                spawn_turn: 0,
                actions: vec![TurnActions::default(); DEFAULT_HORIZON],
            },
        );
        Self {
            map_path,
            horizon: DEFAULT_HORIZON,
            team,
            next_id: 1,
        }
    }

    /// Action queue for `(unit, turn)`, or empty if unscripted.
    #[must_use]
    pub fn actions(&self, opening_id: u32, turn: usize) -> &[Action] {
        let Some(plan) = self.team.units.get(&opening_id) else {
            return &[];
        };
        if turn < plan.spawn_turn {
            return &[];
        }
        let i = turn - plan.spawn_turn;
        plan.actions.get(i).map_or(&[][..], |t| &t.items[..])
    }

    /// Add `action` to `(unit, turn)`'s queue. If an action of the same
    /// category (Move / Primary / Marker) is already queued for this
    /// turn, it is replaced — game rules allow at most one of each per
    /// round. `Destroy` is the exception: it stacks freely.
    /// Returns `false` if the unit doesn't exist or `turn` is outside
    /// its lifetime.
    pub fn append_action(&mut self, opening_id: u32, turn: usize, action: Action) -> bool {
        let Some(plan) = self.team.units.get_mut(&opening_id) else {
            return false;
        };
        if turn < plan.spawn_turn {
            return false;
        }
        let i = turn - plan.spawn_turn;
        let Some(slot) = plan.actions.get_mut(i) else {
            return false;
        };
        if let Some(cat) = action.category() {
            if let Some(existing) = slot.items.iter_mut().find(|a| a.category() == Some(cat)) {
                *existing = action;
                return true;
            }
        }
        slot.items.push(action);
        true
    }

    /// Remove the `idx`-th action from `(unit, turn)`'s queue.
    pub fn remove_action(&mut self, opening_id: u32, turn: usize, idx: usize) -> bool {
        let Some(plan) = self.team.units.get_mut(&opening_id) else {
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

    /// Walk the queue tree from the core down, allocating `UnitPlan`s
    /// for every creating action and pruning plans whose creating
    /// action no longer exists. Idempotent.
    ///
    /// A child's identity is `(parent_opening_id, spawn_turn)` —
    /// builders/turrets only act once per turn, so this pair is
    /// unique. Existing plans with that key are reused (their action
    /// queues survive); new keys allocate a fresh sparse id.
    pub fn ensure_unit_tree(&mut self) {
        let horizon = self.horizon;

        // BFS from the core. `wanted` collects every UnitPlan ID that
        // should remain after pruning.
        let mut wanted: std::collections::HashSet<u32> = std::collections::HashSet::new();
        wanted.insert(CORE_OPENING_ID);
        let mut queue = std::collections::VecDeque::from([CORE_OPENING_ID]);

        while let Some(parent_id) = queue.pop_front() {
            let creating: Vec<(usize, UnitKind)> = {
                let Some(parent) = self.team.units.get(&parent_id) else {
                    continue;
                };
                parent
                    .actions
                    .iter()
                    .enumerate()
                    .flat_map(|(rel, ta)| {
                        let parent_spawn = parent.spawn_turn;
                        ta.items.iter().filter_map(move |a| {
                            a.creates_unit().map(|kind| (parent_spawn + rel + 1, kind))
                        })
                    })
                    .collect()
            };

            for (spawn_turn, kind) in creating {
                if spawn_turn >= horizon {
                    continue;
                }
                let existing: Option<u32> = self
                    .team
                    .units
                    .iter()
                    .find(|(_, p)| p.parent == Some(parent_id) && p.spawn_turn == spawn_turn)
                    .map(|(&id, _)| id);

                let child_id = if let Some(id) = existing {
                    if let Some(p) = self.team.units.get_mut(&id) {
                        p.kind = kind;
                        let n = horizon - spawn_turn;
                        if p.actions.len() < n {
                            p.actions.resize(n, TurnActions::default());
                        } else if p.actions.len() > n {
                            p.actions.truncate(n);
                        }
                    }
                    id
                } else {
                    let id = self.next_id.max(1);
                    self.next_id = id + 1;
                    let n = horizon - spawn_turn;
                    self.team.units.insert(
                        id,
                        UnitPlan {
                            kind,
                            parent: Some(parent_id),
                            spawn_turn,
                            actions: vec![TurnActions::default(); n],
                        },
                    );
                    id
                };
                wanted.insert(child_id);
                queue.push_back(child_id);
            }
        }

        self.team.units.retain(|id, _| wanted.contains(id));
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct TeamPlan {
    /// `opening_id` → `UnitPlan`. 0 is always the core; other IDs are
    /// sparse and never reused.
    pub units: HashMap<u32, UnitPlan>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct UnitPlan {
    pub kind: UnitKind,
    /// Opening ID of the unit whose creating action produced this
    /// one. `None` only for the core.
    pub parent: Option<u32>,
    pub spawn_turn: usize,
    pub actions: Vec<TurnActions>,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, Eq, PartialEq)]
pub enum UnitKind {
    Core,
    Builder,
    Gunner,
    Sentinel,
    Breach,
    Launcher,
}

impl UnitKind {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Core => "core",
            Self::Builder => "builder",
            Self::Gunner => "gunner",
            Self::Sentinel => "sentinel",
            Self::Breach => "breach",
            Self::Launcher => "launcher",
        }
    }
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

/// Game-rule categories that limit at most one action per turn.
/// `Destroy` is intentionally absent (unlimited per round).
#[derive(Copy, Clone, Eq, PartialEq, Debug)]
pub enum ActionCategory {
    /// Builder movement (one per turn).
    Move,
    /// Primary action consuming action_cooldown: build / heal / attack /
    /// spawn (core) / rotate (turret).
    Primary,
    /// Marker placement (one per round, separate from action cooldown).
    Marker,
}

impl Action {
    /// Category for the one-per-turn rule, or `None` if unlimited.
    #[must_use]
    pub const fn category(&self) -> Option<ActionCategory> {
        match self {
            Self::Move { .. } => Some(ActionCategory::Move),
            Self::PlaceMarker { .. } => Some(ActionCategory::Marker),
            Self::Destroy { .. } => None,
            _ => Some(ActionCategory::Primary),
        }
    }

    /// If this action creates a new unit with its own action plan,
    /// returns the kind of that unit.
    #[must_use]
    pub const fn creates_unit(&self) -> Option<UnitKind> {
        match self {
            Self::Spawn { .. } => Some(UnitKind::Builder),
            Self::BuildGunner { .. } => Some(UnitKind::Gunner),
            Self::BuildSentinel { .. } => Some(UnitKind::Sentinel),
            Self::BuildBreach { .. } => Some(UnitKind::Breach),
            Self::BuildLauncher { .. } => Some(UnitKind::Launcher),
            _ => None,
        }
    }

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
