use std::path::{Path, PathBuf};
use std::sync::Arc;

use cambc_proto as proto;
use eframe::egui;
use prost::Message;
use titan_core::map::BG_COLOR;
use titan_core::tile::{MIN_ZOOM, clamp_pan, tile_rect};
use titan_core::{ResponseExt, SpriteSet};

use crate::entities::render_entities;
use crate::opening::Opening;
use crate::sim::{Cursor, Sim};

const SELECTION_STROKE: egui::Color32 = egui::Color32::from_rgb(0xff, 0xc0, 0x40);

pub struct App {
    pub atlas: Arc<SpriteSet>,
    pub map: proto::Map,
    pub map_path: PathBuf,
    pub opening: Opening,
    pub sim: Sim,
    pub opening_path: Option<PathBuf>,

    pub pan: egui::Vec2,
    pub zoom: f32,
    pub cached_map_shapes: Vec<egui::Shape>,
    pub cached_map_origin: egui::Vec2,
    pub cached_map_zoom: f32,

    /// Turn whose action queue the sidebar is editing. The sim is always
    /// advanced to `(edit_turn + 1, 0)` so the map shows the *result*
    /// of running this turn — actions take visible effect immediately.
    pub edit_turn: usize,

    /// Engine ID of the unit currently selected on the map (if any).
    pub selected: Option<i32>,
    /// Overlay each unit's engine ID on its tile.
    pub show_unit_ids: bool,
    /// Hold-chord direction state.
    pub chord: ChordState,
    /// Stack of just-committed actions, for Backspace = undo.
    pub undo_stack: Vec<UndoEntry>,
    /// Most recent user-visible message: commit/undo/save/export
    /// success or failure. Surfaced in the status block at the top of
    /// the sidebar; replaces the old hidden `error` field.
    pub last_event: Option<String>,

    /// Per-action-kind last-used direction. Default N. Used by the
    /// action wheel as the placed direction; updated whenever the
    /// user commits or rotates an action. App-local, lost on close /
    /// new opening.
    pub last_used: std::collections::HashMap<DirectionalAction, i32>,

    /// Open RMB action wheel. None when not picking.
    pub wheel: Option<Wheel>,

    /// Modal text input awaiting a marker value. Set after the user
    /// picks Marker from the wheel; the next frame renders a modal.
    pub marker_prompt: Option<MarkerPrompt>,

    /// Bridge target picker: after picking Bridge from the wheel we
    /// remember the source so the next RMB click sets the target.
    pub bridge_pending: Option<BridgePending>,

    /// State diff for `edit_turn`: builder movements and dirtied
    /// tiles. Repopulated every `refresh_sim`. Drives the in-map
    /// arrow / highlight overlay so the user sees what changed in
    /// the turn they're currently authoring.
    pub turn_diff: Option<TurnDiff>,

    /// When `Some`, a save was attempted at a path that already
    /// exists and the user must confirm before we overwrite. The
    /// modal renders next frame; clicking Overwrite calls
    /// `force_save_to(path)`.
    pub overwrite_prompt: Option<PathBuf>,
}

/// What changed during the current `edit_turn`.
#[derive(Clone, Debug, Default)]
pub struct TurnDiff {
    /// `(from, to)` per builder that moved this turn.
    pub moves: Vec<((i32, i32), (i32, i32))>,
    /// Tiles where an entity appeared or disappeared this turn.
    pub dirtied: std::collections::HashSet<(i32, i32)>,
}

/// Action types that have a `dir` parameter and therefore participate
/// in the per-session "last-used direction" memory. Rotate / Fire /
/// Throw aren't authored, so they're absent.
#[derive(Copy, Clone, Eq, PartialEq, Hash, Debug)]
pub enum DirectionalAction {
    Conveyor,
    ArmConv,
    Splitter,
    Gunner,
    Sentinel,
    Breach,
    Spawn,
    Move,
}

#[derive(Clone, Debug)]
pub struct Wheel {
    /// Target tile clicked to open the wheel.
    pub target: (i32, i32),
    /// Centre of the wheel in screen space.
    pub centre: egui::Pos2,
    /// The unit the wheel was opened for.
    pub uid: i32,
    /// Wedges to render, in order around the circle.
    pub options: Vec<Pending>,
}

#[derive(Clone, Debug)]
pub struct MarkerPrompt {
    pub target: (i32, i32),
    pub uid: i32,
    /// Current text in the input box. Parsed on submit.
    pub buffer: String,
}

#[derive(Clone, Debug)]
pub struct BridgePending {
    /// Source tile (the original RMB click).
    pub source: (i32, i32),
    pub uid: i32,
}

/// Per-frame state for the hold-chord direction input.
///
/// Bare aim — hold any subset of `h j k l`, plus optionally `;` (centre)
/// — and release without a tool letter to commit the unit's primary
/// action (Move/Spawn/Rotate) toward the accumulated direction.
///
/// Or hold a tool letter (after at least one direction key) to *arm* a
/// build action. While the tool letter remains held, every subsequent
/// chord cycle is collected: for bridges it appends one step to the
/// target vector; for directional non-bridge buildings the first
/// cycle sets the facing. Releasing the tool letter commits the
/// accumulated action.
#[derive(Default)]
pub struct ChordState {
    /// Direction mask held last frame. bits: N=1 (k), E=2 (l),
    /// S=4 (j), W=8 (h), Centre=16 (`;`).
    pub last_mask: u8,
    /// Peak mask seen during the current hold cycle.
    pub max_mask: u8,
    /// When `Some`, the editor is in build-armed state: the user is
    /// holding a tool letter and we're collecting target / facing /
    /// bridge-vector inputs until they release it.
    pub armed: Option<ArmedState>,
}

/// Inflight build whose tool letter is still being held. Captured
/// when the user pressed the tool letter while a chord direction was
/// already held; committed when they release the tool letter.
#[derive(Clone, Debug)]
pub struct ArmedState {
    pub tool: Pending,
    /// The egui key for the held tool letter, used to detect release.
    pub tool_key: egui::Key,
    /// Direction of chord1 (the chord held when the tool was pressed).
    /// 0..=7 is an 8-way compass; 8 is Centre (build on own tile).
    pub target_dir: i32,
    /// Optional facing direction set by a chord cycle made *after* the
    /// tool letter went down. Defaults to `target_dir` if unset.
    pub facing: Option<i32>,
    /// Bridge target vector accumulated from chord cycles after arm.
    /// Only meaningful when `tool == Pending::BuildBridge`.
    pub bridge_vector: (i32, i32),
}

/// One undoable commit. We store the entire pre-mutation `Opening`
/// snapshot — index-based deltas would drift stale when later commits
/// replace a same-category action, when the sidebar ✕ shifts indices,
/// or when `ensure_unit_tree` prunes a `UnitPlan` whose creating action
/// got removed. Snapshots are small (a few KB) and restoration is
/// trivial.
#[derive(Clone, Debug)]
pub struct UndoEntry {
    /// Snapshot of `Opening` before the commit that produced this
    /// entry. `undo_last` swaps `self.opening` back to this.
    pub before: Opening,
    /// Short label of what the commit did, for the status line on
    /// undo. Cosmetic.
    pub label: String,
}

/// Action template waiting for a target tile. The user clicks on the
/// map; the editor synthesises the full action with that tile as the
/// Tool kind that can be armed via chord or picked from the action
/// wheel. Heal, Attack, Rotate, Fire, and Throw are intentionally
/// absent — opening books don't author them (allied buildings get
/// destroyed for free; turret/launcher facing and firing aren't
/// useful in the opening phase before opponent positions are known).
#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
pub enum Pending {
    BuildConveyor,
    BuildArmouredConveyor,
    BuildSplitter,
    BuildBridge,
    BuildHarvester,
    BuildRoad,
    BuildBarrier,
    BuildGunner,
    BuildSentinel,
    BuildBreach,
    BuildLauncher,
    BuildFoundry,
    Destroy,
    Marker,
    /// Core action: spawn a builder on one of the 9 core tiles.
    Spawn,
}

impl Pending {
    /// True if this build has a `dir` field — the action wheel
    /// applies `last_used` direction to these.
    #[must_use]
    pub const fn directional(self) -> bool {
        matches!(
            self,
            Self::BuildConveyor
                | Self::BuildArmouredConveyor
                | Self::BuildSplitter
                | Self::BuildGunner
                | Self::BuildSentinel
                | Self::BuildBreach
        )
    }

    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::BuildConveyor => "Conveyor",
            Self::BuildArmouredConveyor => "ArmConv",
            Self::BuildSplitter => "Splitter",
            Self::BuildBridge => "Bridge",
            Self::BuildHarvester => "Harvester",
            Self::BuildRoad => "Road",
            Self::BuildBarrier => "Barrier",
            Self::BuildGunner => "Gunner",
            Self::BuildSentinel => "Sentinel",
            Self::BuildBreach => "Breach",
            Self::BuildLauncher => "Launcher",
            Self::BuildFoundry => "Foundry",
            Self::Destroy => "Destroy",
            Self::Marker => "Marker",
            Self::Spawn => "Spawn",
        }
    }
}

impl App {
    #[must_use] 
    pub fn new(
        atlas: Arc<SpriteSet>,
        map: proto::Map,
        map_path: PathBuf,
        opening: Opening,
    ) -> Self {
        let sim = Sim::from_map(&map_path).expect("sim init");
        let mut app = Self {
            atlas,
            map,
            map_path,
            opening,
            sim,
            opening_path: None,
            pan: egui::Vec2::new(10.0, 10.0),
            zoom: 1.0,
            cached_map_shapes: Vec::new(),
            cached_map_origin: egui::Vec2::ZERO,
            cached_map_zoom: 0.0,
            edit_turn: 0,
            selected: None,
            show_unit_ids: true,
            chord: ChordState::default(),
            undo_stack: Vec::new(),
            last_event: None,
            last_used: std::collections::HashMap::new(),
            wheel: None,
            marker_prompt: None,
            bridge_pending: None,
            turn_diff: None,
            overwrite_prompt: None,
        };
        app.refresh_sim();
        app
    }

    /// Look up `last_used[kind]`, defaulting to North if unset.
    fn last_used_dir(&self, kind: DirectionalAction) -> i32 {
        self.last_used.get(&kind).copied().unwrap_or(0)
    }

    /// Update `last_used[kind]` to `dir`.
    fn set_last_used(&mut self, kind: DirectionalAction, dir: i32) {
        self.last_used.insert(kind, dir);
    }

    /// RMB click on a tile with a unit selected. Opens the action
    /// wheel containing every action that unit can author. The
    /// engine validates the (action, target tile) pair at commit
    /// time and surfaces any out-of-range / illegal placements as
    /// sim errors in the status block.
    fn try_open_wheel(&mut self, gx: i32, gy: i32, screen_pos: egui::Pos2) {
        let Some(uid) = self.selected else { return };
        if self.sim.engine_to_opening.get(&uid).is_none() {
            return;
        }
        let Some(e) = self.sim.game.entities.get(&uid) else {
            return;
        };
        let options = wheel_options_for(e);
        if options.is_empty() {
            return;
        }
        self.wheel = Some(Wheel {
            target: (gx, gy),
            centre: screen_pos,
            uid,
            options,
        });
    }

    /// User clicked a wedge in the wheel. Commit the action.
    fn commit_wheel_choice(&mut self, choice: Pending) {
        let Some(wheel) = self.wheel.take() else {
            return;
        };
        let (gx, gy) = wheel.target;
        let uid = wheel.uid;
        let Some(&opening_id) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };

        match choice {
            Pending::BuildBridge => {
                self.bridge_pending = Some(BridgePending {
                    source: (gx, gy),
                    uid,
                });
                self.last_event = Some(format!(
                    "bridge source ({gx},{gy}) — RMB target tile (dist²≤9)"
                ));
            }
            Pending::Marker => {
                self.marker_prompt = Some(MarkerPrompt {
                    target: (gx, gy),
                    uid,
                    buffer: String::new(),
                });
            }
            Pending::Spawn => {
                // Spawn target = (gx, gy); engine takes a Direction
                // which we derive from (target − core_centre). The
                // wheel only opens for tiles within the 3x3 so this
                // is a valid 9-way map (0..=7 plus Centre).
                let Some(core) = self.sim.game.entities.get(&uid) else {
                    return;
                };
                let dx = gx - core.position.x;
                let dy = gy - core.position.y;
                let dir = vec_to_dir((dx, dy));
                // (0,0) is centre; vec_to_dir maps that to N — fix:
                let dir = if dx == 0 && dy == 0 { 8 } else { dir };
                self.append_tracked(
                    opening_id,
                    self.edit_turn,
                    crate::opening::Action::Spawn { dir },
                );
                self.set_last_used(DirectionalAction::Spawn, dir);
            }
            other => {
                let dir = directional_kind_for(other).map(|k| self.last_used_dir(k));
                let action = self.build_action(other, gx, gy, dir);
                self.append_tracked(opening_id, self.edit_turn, action);
                if let (Some(kind), Some(d)) = (directional_kind_for(other), dir) {
                    self.set_last_used(kind, d);
                }
            }
        }
    }

    /// Commit a Bridge action with its source/target pair. Called
    /// when the user RMB-clicks a target tile after picking Bridge.
    fn commit_bridge(&mut self, bp: BridgePending, tx: i32, ty: i32) {
        let dx = tx - bp.source.0;
        let dy = ty - bp.source.1;
        let dist_sq = dx * dx + dy * dy;
        if dist_sq == 0 || dist_sq > 9 {
            self.last_event = Some(format!(
                "bridge target ({tx},{ty}) out of range (need dist²≤9)"
            ));
            return;
        }
        let Some(&opening_id) = self.sim.engine_to_opening.get(&bp.uid) else {
            return;
        };
        let action = crate::opening::Action::BuildBridge {
            x: bp.source.0,
            y: bp.source.1,
            tx,
            ty,
        };
        self.append_tracked(opening_id, self.edit_turn, action);
    }

    /// Shift+RMB: move builder one step in the (gx,gy) direction. If
    /// the target is unwalkable but the underlying tile is empty/Ti/Ax
    /// ore, queue `BuildRoad` first so the move lands on the road.
    fn handle_shift_rmb(&mut self, gx: i32, gy: i32) {
        let Some(uid) = self.selected else { return };
        let Some(&opening_id) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };
        let Some(e) = self.sim.game.entities.get(&uid) else {
            return;
        };
        if !matches!(e, libre_engine::game_map::Entity::BuilderBot(_)) {
            self.last_event = Some("shift+RMB: only builders can move".into());
            return;
        }
        let dx = gx - e.position.x;
        let dy = gy - e.position.y;
        if dx.abs() > 1 || dy.abs() > 1 || (dx == 0 && dy == 0) {
            self.last_event = Some("shift+RMB: must be one of 8 adjacent tiles".into());
            return;
        }
        let dir = vec_to_dir((dx, dy));
        let env = self.map_env(gx, gy);
        let walkable = matches!(
            env,
            proto::Environment::EnvEmpty
                | proto::Environment::EnvOreTitanium
                | proto::Environment::EnvOreAxionite
        );
        let walkable_with_building =
            self.sim.game.entities.values().any(|ent| {
                ent.position.x == gx && ent.position.y == gy && is_walkable_building(ent)
            });
        if walkable_with_building {
            // Tile already has a walkable building; just move.
            self.append_tracked(
                opening_id,
                self.edit_turn,
                crate::opening::Action::Move { dir },
            );
        } else if walkable {
            // Empty/ore: pre-place a road, then move.
            self.append_tracked(
                opening_id,
                self.edit_turn,
                crate::opening::Action::BuildRoad { x: gx, y: gy },
            );
            self.append_tracked(
                opening_id,
                self.edit_turn,
                crate::opening::Action::Move { dir },
            );
        } else {
            self.last_event = Some(format!("shift+RMB: ({gx},{gy}) not walkable"));
        }
    }

    /// Shift+MMB: queue Destroy for the friendly building at (gx,gy).
    fn queue_destroy_at(&mut self, gx: i32, gy: i32) {
        let Some(uid) = self.selected else { return };
        let Some(&opening_id) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };
        let Some(e) = self.sim.game.entities.get(&uid) else {
            return;
        };
        if !matches!(e, libre_engine::game_map::Entity::BuilderBot(_)) {
            self.last_event = Some("shift+MMB: only builders can destroy".into());
            return;
        }
        // The tile must hold one of *our* buildings.
        let has_friendly_building = self.sim.game.entities.values().any(|ent| {
            ent.position.x == gx
                && ent.position.y == gy
                && ent.team == e.team
                && !matches!(ent, libre_engine::game_map::Entity::BuilderBot(_))
        });
        if !has_friendly_building {
            self.last_event = Some(format!("shift+MMB: no building at ({gx},{gy})"));
            return;
        }
        self.append_tracked(
            opening_id,
            self.edit_turn,
            crate::opening::Action::Destroy { x: gx, y: gy },
        );
    }

    /// MMB click on a tile that has a queued directional action:
    /// cycle its `dir` field through 8 directions and update the
    /// per-kind last-used so subsequent placements use the new dir.
    fn rotate_queued_at(&mut self, gx: i32, gy: i32) {
        let Some(uid) = self.selected else { return };
        let Some(&opening_id) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };
        let turn = self.edit_turn;
        let snapshot = self.opening.clone();
        let rotated: Option<(DirectionalAction, i32, String)> = {
            let Some(plan) = self.opening.team.units.get_mut(&opening_id) else {
                return;
            };
            if turn < plan.spawn_turn {
                return;
            }
            let i = turn - plan.spawn_turn;
            let Some(slot) = plan.actions.get_mut(i) else {
                return;
            };
            slot.items
                .iter_mut()
                .find(|a| action_target_at(a, gx, gy))
                .and_then(|action| {
                    rotate_action_dir(action).map(|(kind, dir)| (kind, dir, action.label()))
                })
        };
        if let Some((kind, new_dir, label)) = rotated {
            self.undo_stack.push(UndoEntry {
                before: snapshot,
                label: format!("rotate {label}"),
            });
            self.set_last_used(kind, new_dir);
            self.last_event = Some(format!("rotated {label} → {}", name_for(new_dir)));
            self.refresh_sim();
        }
    }

    /// Build the queued `Action` for a wheel pick. Bridge / Marker /
    /// Spawn are handled before this is called.
    fn build_action(
        &self,
        choice: Pending,
        x: i32,
        y: i32,
        dir: Option<i32>,
    ) -> crate::opening::Action {
        let dir = dir.unwrap_or(0);
        match choice {
            Pending::BuildConveyor => crate::opening::Action::BuildConveyor { x, y, dir },
            Pending::BuildArmouredConveyor => {
                crate::opening::Action::BuildArmouredConveyor { x, y, dir }
            }
            Pending::BuildSplitter => crate::opening::Action::BuildSplitter { x, y, dir },
            Pending::BuildHarvester => crate::opening::Action::BuildHarvester { x, y },
            Pending::BuildRoad => crate::opening::Action::BuildRoad { x, y },
            Pending::BuildBarrier => crate::opening::Action::BuildBarrier { x, y },
            Pending::BuildGunner => crate::opening::Action::BuildGunner { x, y, dir },
            Pending::BuildSentinel => crate::opening::Action::BuildSentinel { x, y, dir },
            Pending::BuildBreach => crate::opening::Action::BuildBreach { x, y, dir },
            Pending::BuildLauncher => crate::opening::Action::BuildLauncher { x, y },
            Pending::BuildFoundry => crate::opening::Action::BuildFoundry { x, y },
            Pending::Destroy => crate::opening::Action::Destroy { x, y },
            Pending::BuildBridge | Pending::Marker | Pending::Spawn => {
                // Handled before reaching here. Fall back to a no-op
                // marker so the type-checker is happy; the caller
                // should never feed these in.
                crate::opening::Action::PlaceMarker { x, y, value: 0 }
            }
        }
    }

    /// Dispatch a direction key: Move on builders, Spawn on cores.
    /// Turrets/launchers don't author actions via direction keys
    /// (rotation/firing/throwing aren't supported by the editor).
    fn dir_key(&mut self, dir: i32) {
        let Some(uid) = self.selected else { return };
        let Some(&opening_id) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };
        let Some(e) = self.sim.game.entities.get(&uid) else {
            return;
        };
        let action = match e {
            libre_engine::game_map::Entity::BuilderBot(_) => crate::opening::Action::Move { dir },
            libre_engine::game_map::Entity::Core(_) => crate::opening::Action::Spawn { dir },
            _ => return,
        };
        self.append_tracked(opening_id, self.edit_turn, action);
    }

    /// Append `action` and stash a snapshot so Backspace can revert.
    /// Returns true on success.
    fn append_tracked(
        &mut self,
        opening_id: u32,
        turn: usize,
        action: crate::opening::Action,
    ) -> bool {
        let label = action.label();
        let snapshot = self.opening.clone();
        if !self.opening.append_action(opening_id, turn, action) {
            self.last_event = Some(format!("rejected: {label}"));
            return false;
        }
        self.undo_stack.push(UndoEntry {
            before: snapshot,
            label: format!("T{turn}: {label}"),
        });
        self.last_event = Some(format!("queued T{turn}: {label}"));
        self.opening.ensure_unit_tree();
        self.refresh_sim();
        true
    }

    /// Restore the most recent pre-commit snapshot. Robust against
    /// same-category replacement, sidebar ✕ deletes, and tree
    /// pruning — all of which broke the old idx-based undo.
    fn undo_last(&mut self) {
        if let Some(entry) = self.undo_stack.pop() {
            self.opening = entry.before;
            self.last_event = Some(format!("undone {}", entry.label));
            self.refresh_sim();
        } else {
            self.last_event = Some("nothing to undo".into());
        }
    }

    /// Build the action queued by an armed chord and append it to the
    /// selected unit's queue.
    ///
    /// `target_dir` selects the tile relative to the unit (one step in
    /// each compass direction; Centre = own tile). For directional
    /// non-bridge buildings, `facing` defaults to `target_dir` if the
    /// user didn't supply a separate facing chord. For bridges, the
    /// source is `target_dir`'s tile and the destination is
    /// `source + bridge_vector` (each step in `bridge_vector` came
    /// from one chord cycle while the tool was held).
    fn commit_armed(&mut self, armed: &ArmedState) {
        let Some(uid) = self.selected else { return };
        let Some(e) = self.sim.game.entities.get(&uid) else {
            return;
        };
        let pos = e.position;
        let (dx, dy) = dir_delta(armed.target_dir);
        let (tx, ty) = (pos.x + dx, pos.y + dy);
        let facing = armed.facing.unwrap_or(armed.target_dir);

        let action = match armed.tool {
            Pending::BuildConveyor => crate::opening::Action::BuildConveyor {
                x: tx,
                y: ty,
                dir: facing,
            },
            Pending::BuildArmouredConveyor => crate::opening::Action::BuildArmouredConveyor {
                x: tx,
                y: ty,
                dir: facing,
            },
            Pending::BuildSplitter => crate::opening::Action::BuildSplitter {
                x: tx,
                y: ty,
                dir: facing,
            },
            Pending::BuildBridge => crate::opening::Action::BuildBridge {
                x: tx,
                y: ty,
                tx: tx + armed.bridge_vector.0,
                ty: ty + armed.bridge_vector.1,
            },
            Pending::BuildHarvester => crate::opening::Action::BuildHarvester { x: tx, y: ty },
            Pending::BuildRoad => crate::opening::Action::BuildRoad { x: tx, y: ty },
            Pending::BuildBarrier => crate::opening::Action::BuildBarrier { x: tx, y: ty },
            Pending::BuildGunner => crate::opening::Action::BuildGunner {
                x: tx,
                y: ty,
                dir: facing,
            },
            Pending::BuildSentinel => crate::opening::Action::BuildSentinel {
                x: tx,
                y: ty,
                dir: facing,
            },
            Pending::BuildBreach => crate::opening::Action::BuildBreach {
                x: tx,
                y: ty,
                dir: facing,
            },
            Pending::BuildLauncher => crate::opening::Action::BuildLauncher { x: tx, y: ty },
            Pending::BuildFoundry => crate::opening::Action::BuildFoundry { x: tx, y: ty },
            Pending::Destroy => crate::opening::Action::Destroy { x: tx, y: ty },
            Pending::Marker => crate::opening::Action::PlaceMarker {
                x: tx,
                y: ty,
                value: 0,
            },
            Pending::Spawn => crate::opening::Action::Spawn {
                dir: armed.target_dir,
            },
        };

        let Some(&opening_id) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };
        self.append_tracked(opening_id, self.edit_turn, action);
    }

    /// Tree-axis selection: move up/down the player's unit lanes.
    /// Lane order is the opening-id BFS layout (cores first, then
    /// children in spawn order). Used by Up/Down arrow keys and by
    /// click/drag in the tree panel.
    fn move_selection_lane(&mut self, delta: i32) {
        let lanes = unit_lanes(&self.opening);
        if lanes.is_empty() {
            return;
        }
        // Map current selection to its lane index, or default to 0.
        let cur_lane = self
            .selected
            .and_then(|uid| self.sim.engine_to_opening.get(&uid).copied())
            .and_then(|oid| lanes.iter().position(|&l| l == oid))
            .unwrap_or(0);
        let new_lane = (cur_lane as i32 + delta).rem_euclid(lanes.len() as i32) as usize;
        let target_oid = lanes[new_lane];
        // Find the engine_id mapped to this opening_id, if alive at
        // edit_turn. If the unit isn't yet alive at the displayed
        // frame, leave selection latent (no engine binding).
        let engine_id = self
            .sim
            .engine_to_opening
            .iter()
            .find(|&(_, &oid)| oid == target_oid)
            .map(|(&eid, _)| eid);
        match engine_id {
            Some(eid) => self.select_unit(eid),
            None => self.select_opening_id_latent(target_oid),
        }
    }

    /// Latent-select a unit by opening id. The engine entity may not
    /// exist yet at `edit_turn`; selection is preserved so when time
    /// advances past `spawn_turn` the binding resolves automatically.
    fn select_opening_id_latent(&mut self, target_oid: u32) {
        // Park the selection on a sentinel engine_id we'll resolve on
        // next refresh. Easiest: record the desired opening id and
        // resolve at every refresh_sim. For now, just clear `selected`
        // and remember the desired opening id via edit_turn jump.
        if let Some(plan) = self.opening.team.units.get(&target_oid) {
            let last = self.opening.horizon.saturating_sub(1);
            if plan.spawn_turn > self.edit_turn {
                self.edit_turn = plan.spawn_turn.min(last);
                self.refresh_sim();
                if let Some((&eid, _)) = self
                    .sim
                    .engine_to_opening
                    .iter()
                    .find(|&(_, &oid)| oid == target_oid)
                {
                    self.selected = Some(eid);
                }
            }
        }
    }

    /// Set `selected` to `uid` and, if the unit's opening lifetime
    /// starts after the current `edit_turn`, jump `edit_turn` forward
    /// to its first valid turn so queued actions actually go into a
    /// real slot. Without this, selecting a freshly-spawned builder at
    /// turn 0 (it doesn't exist until turn 1) silently rejects every
    /// action commit.
    fn select_unit(&mut self, uid: i32) {
        self.selected = Some(uid);
        if let Some(&opening_id) = self.sim.engine_to_opening.get(&uid)
            && let Some(plan) = self.opening.team.units.get(&opening_id)
            && plan.spawn_turn > self.edit_turn
        {
            let last = self.opening.horizon.saturating_sub(1);
            self.edit_turn = plan.spawn_turn.min(last);
            self.refresh_sim();
        }
    }

    /// Advance the sim cursor to the post-`edit_turn` state and
    /// recompute the per-turn visual diff (builder movements +
    /// dirtied tiles). The map renders both as overlays so the user
    /// sees what their currently-authored turn does.
    fn refresh_sim(&mut self) {
        let edit_turn = self.edit_turn;
        // Step 1: seek to start of edit_turn.
        if let Err(errs) = self.sim.seek(
            &self.opening,
            Cursor {
                turn: edit_turn,
                unit_idx: 0,
            },
        ) {
            self.last_event = Some(format!("{} sim error(s)", errs.len()));
            self.turn_diff = None;
            return;
        }
        // Snapshot pre-turn entity positions / ids.
        let before_pos: std::collections::HashMap<i32, (i32, i32)> = self
            .sim
            .game
            .entities
            .iter()
            .map(|(&id, e)| (id, (e.position.x, e.position.y)))
            .collect();
        let before_ids: std::collections::HashSet<i32> = before_pos.keys().copied().collect();
        let builders_before: std::collections::HashSet<i32> = self
            .sim
            .game
            .entities
            .iter()
            .filter(|(_, e)| matches!(e, libre_engine::game_map::Entity::BuilderBot(_)))
            .map(|(&id, _)| id)
            .collect();

        // Step 2: run edit_turn (if within horizon).
        if edit_turn < self.opening.horizon {
            let errs = self.sim.step_turn(&self.opening);
            if !errs.is_empty() {
                self.last_event = Some(format!("{} sim error(s) in T{edit_turn}", errs.len()));
            }
        }

        // Diff.
        let mut diff = TurnDiff::default();
        let after_ids: std::collections::HashSet<i32> =
            self.sim.game.entities.keys().copied().collect();
        // Appearances: tiles where new entities sit post-turn.
        for &id in after_ids.difference(&before_ids) {
            if let Some(e) = self.sim.game.entities.get(&id) {
                diff.dirtied.insert((e.position.x, e.position.y));
            }
        }
        // Disappearances: tiles where entities used to sit pre-turn.
        for &id in before_ids.difference(&after_ids) {
            if let Some(&pos) = before_pos.get(&id) {
                diff.dirtied.insert(pos);
            }
        }
        // Builder movements: same id, different position, builder kind.
        for &id in &builders_before {
            let Some(e) = self.sim.game.entities.get(&id) else {
                continue;
            };
            let after = (e.position.x, e.position.y);
            let Some(&before) = before_pos.get(&id) else {
                continue;
            };
            if before != after {
                diff.moves.push((before, after));
            }
        }
        self.turn_diff = Some(diff);
    }

    fn map_env(&self, x: i32, y: i32) -> proto::Environment {
        let row = self.map.rows.get(y as usize);
        let tile = row.and_then(|r| r.tiles.get(x as usize)).copied();
        tile.and_then(|t| proto::Environment::try_from(t).ok())
            .unwrap_or(proto::Environment::EnvEmpty)
    }

    /// Find the engine ID of an *author-able player-team unit* on
    /// tile `(x, y)`. Buildings (roads, conveyors, etc.) and team B
    /// entities are intentionally not returned — the editor only
    /// authors actions for the player's units, so selecting a road
    /// or an enemy core is meaningless and only causes confusion.
    /// If multiple authored units share the tile (e.g. a builder
    /// standing on its own road), the builder takes priority.
    fn entity_at(&self, x: i32, y: i32) -> Option<i32> {
        use libre_engine::game_map::Entity;
        let mut hit_id: Option<i32> = None;
        for (&id, e) in &self.sim.game.entities {
            // Player-team only. Team B isn't represented in the
            // opening, so its entities aren't selectable.
            if !matches!(e.team, libre_engine::common::Team::A) {
                continue;
            }
            let p = e.position;
            let on_tile = match e {
                Entity::Core(_) => (x - p.x).abs() <= 1 && (y - p.y).abs() <= 1,
                _ => p.x == x && p.y == y,
            };
            if !on_tile {
                continue;
            }
            // Only authorable kinds. Buildings (Conveyor, Road, etc.)
            // have no UnitPlan so selecting them is a dead end.
            let authorable = matches!(
                e,
                Entity::Core(_)
                    | Entity::BuilderBot(_)
                    | Entity::Gunner(_)
                    | Entity::Sentinel(_)
                    | Entity::Breach(_)
                    | Entity::Launcher(_)
            );
            if !authorable {
                continue;
            }
            // Prefer builders (typically the unit standing on top).
            if matches!(e, Entity::BuilderBot(_)) {
                return Some(id);
            }
            hit_id = Some(id);
        }
        hit_id
    }
}

impl titan_core::ModeApp for App {
    fn name(&self) -> &'static str {
        "opening"
    }
    fn current_path(&self) -> Option<&Path> {
        self.opening_path.as_deref()
    }
    fn pick_extensions(&self) -> &'static [&'static str] {
        &["opening", "map26"]
    }
    fn pick_default_dir(&self, config: &titan_core::CambcConfig) -> PathBuf {
        config.maps_path()
    }
    fn open_path(&mut self, path: PathBuf) -> Result<(), String> {
        let bytes =
            std::fs::read(&path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or_default();
        let (opening, opening_path) = if ext == "map26" {
            // Bare map: start a fresh opening referencing it.
            (Opening::empty(path.clone()), None)
        } else {
            let op: Opening =
                serde_json::from_slice(&bytes).map_err(|e| format!("invalid opening file: {e}"))?;
            (op, Some(path))
        };
        let map_bytes = std::fs::read(&opening.map_path)
            .map_err(|e| format!("cannot read map {}: {e}", opening.map_path.display()))?;
        let map = proto::Map::decode(&*map_bytes).map_err(|e| format!("invalid map: {e}"))?;
        let sim = Sim::from_map(&opening.map_path)?;
        self.map_path = opening.map_path.clone();
        self.map = map;
        self.opening = opening;
        self.sim = sim;
        self.opening_path = opening_path;
        // Per-session state — forget last-used directions, in-flight
        // wheel / marker / bridge picker, undo history.
        self.last_used.clear();
        self.wheel = None;
        self.marker_prompt = None;
        self.bridge_pending = None;
        self.undo_stack.clear();
        self.cached_map_shapes.clear();
        self.cached_map_zoom = 0.0;
        self.selected = None;
        self.last_event = None;
        Ok(())
    }
    fn can_save(&self) -> bool {
        true
    }
    fn save_file(&mut self) {
        let path = self
            .opening_path
            .clone()
            .unwrap_or_else(|| self.map_path.with_extension("opening"));
        // Defer to a confirmation modal if we'd be overwriting a file
        // we didn't load from. Saving back to the same `.opening` file
        // we opened goes through immediately — that's the user
        // re-saving, no surprise possible.
        let same_as_loaded = self.opening_path.as_ref() == Some(&path);
        if !same_as_loaded && path.exists() {
            self.overwrite_prompt = Some(path);
            return;
        }
        self.force_save_to(path);
    }
}

impl App {
    /// Write the opening to `path` unconditionally. Caller is
    /// responsible for any overwrite check.
    fn force_save_to(&mut self, path: PathBuf) {
        match serde_json::to_vec_pretty(&self.opening) {
            Ok(bytes) => match std::fs::write(&path, bytes) {
                Ok(()) => {
                    let display = path.display().to_string();
                    self.opening_path = Some(path);
                    let empties = count_empty_unit_turns(&self.opening);
                    self.last_event = if empties > 0 {
                        Some(format!(
                            "saved {display} — warning: {empties} unit-turn(s) have no actions"
                        ))
                    } else {
                        Some(format!("saved {display}"))
                    };
                }
                Err(e) => self.last_event = Some(format!("save: {e}")),
            },
            Err(e) => self.last_event = Some(format!("save: {e}")),
        }
    }
}

/// Count `(unit, turn)` cells where the action queue is empty. Used as
/// a save-time completeness warning.
fn count_empty_unit_turns(opening: &Opening) -> usize {
    let mut n = 0;
    for plan in opening.team.units.values() {
        for slot in &plan.actions {
            if slot.items.is_empty() {
                n += 1;
            }
        }
    }
    n
}

impl titan_core::Playback for App {
    fn position(&self) -> usize {
        self.edit_turn
    }
    fn total(&self) -> usize {
        self.opening.horizon.max(1)
    }
    fn playing(&self) -> bool {
        false
    }
    fn toggle_play(&mut self) {}
    fn step_forward(&mut self, n: usize) {
        let last = self.opening.horizon.saturating_sub(1);
        self.edit_turn = (self.edit_turn + n).min(last);
        self.refresh_sim();
    }
    fn step_back(&mut self, n: usize) {
        self.edit_turn = self.edit_turn.saturating_sub(n);
        self.refresh_sim();
    }
    fn seek(&mut self, position: usize) {
        let last = self.opening.horizon.saturating_sub(1);
        self.edit_turn = position.min(last);
        self.refresh_sim();
    }
    fn speed(&self) -> i32 {
        0
    }
    fn set_speed(&mut self, _speed: i32) {}
    fn supports_step_back(&self) -> bool {
        true
    }
    fn supports_seek(&self) -> bool {
        true
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        // Scratch state read from egui this frame. Pulled out into one
        // input(...) closure so the borrow doesn't escape.
        struct Keys {
            esc: bool,
            space: bool,
            backspace: bool,
            up: bool,
            down: bool,
            mask: u8,
            tool: Option<(egui::Key, Pending)>,
            armed_tool_held: bool,
            digit_dir: Option<i32>,
        }
        let armed_tool_key = self.chord.armed.as_ref().map(|a| a.tool_key);
        let keys = ui.ctx().input(|i| {
            // Held mask. Bits: N=1 (k), E=2 (l), S=4 (j), W=8 (h),
            // Centre=16 (`;`).
            let mask = u8::from(i.key_down(egui::Key::K))
                | (u8::from(i.key_down(egui::Key::L)) << 1)
                | (u8::from(i.key_down(egui::Key::J)) << 2)
                | (u8::from(i.key_down(egui::Key::H)) << 3)
                | (u8::from(i.key_down(egui::Key::Semicolon)) << 4);
            let tool_keys = [
                (egui::Key::C, Pending::BuildConveyor),
                (egui::Key::A, Pending::BuildArmouredConveyor),
                (egui::Key::S, Pending::BuildSplitter),
                (egui::Key::B, Pending::BuildBridge),
                (egui::Key::V, Pending::BuildHarvester),
                (egui::Key::R, Pending::BuildRoad),
                (egui::Key::W, Pending::BuildBarrier),
                (egui::Key::G, Pending::BuildGunner),
                (egui::Key::T, Pending::BuildSentinel),
                (egui::Key::X, Pending::BuildBreach),
                (egui::Key::E, Pending::BuildLauncher),
                (egui::Key::F, Pending::BuildFoundry),
                (egui::Key::D, Pending::Destroy),
            ];
            let tool = tool_keys
                .iter()
                .find(|(k, _)| i.key_pressed(*k))
                .map(|(k, p)| (*k, *p));
            let armed_tool_held = armed_tool_key.is_some_and(|k| i.key_down(k));
            // Numpad-layout digits → 8-way direction. Num5 = Centre.
            let digit_dir = if i.key_pressed(egui::Key::Num8) {
                Some(0)
            } else if i.key_pressed(egui::Key::Num9) {
                Some(1)
            } else if i.key_pressed(egui::Key::Num6) {
                Some(2)
            } else if i.key_pressed(egui::Key::Num3) {
                Some(3)
            } else if i.key_pressed(egui::Key::Num2) {
                Some(4)
            } else if i.key_pressed(egui::Key::Num1) {
                Some(5)
            } else if i.key_pressed(egui::Key::Num4) {
                Some(6)
            } else if i.key_pressed(egui::Key::Num7) {
                Some(7)
            } else if i.key_pressed(egui::Key::Num5) {
                Some(8)
            } else {
                None
            };
            // Ctrl+Z is an alternative undo (Ctrl+Shift+Z reserved
            // for redo if added later).
            let ctrl_z = i.modifiers.command_only() && i.key_pressed(egui::Key::Z);
            Keys {
                esc: i.key_pressed(egui::Key::Escape),
                space: i.key_pressed(egui::Key::Space),
                backspace: i.key_pressed(egui::Key::Backspace) || ctrl_z,
                up: i.key_pressed(egui::Key::ArrowUp),
                down: i.key_pressed(egui::Key::ArrowDown),
                mask,
                tool,
                armed_tool_held,
                digit_dir,
            }
        });

        // Chord state machine. hjkl release and numpad press are
        // interchangeable: both produce a "cycle direction" that
        // feeds the same logic.
        //
        //   Idle (no tool armed):
        //     - cycle dir → primary action (Move/Spawn/Rotate).
        //     - tool letter pressed while a chord is held OR with a
        //       same-frame numpad press → arm with that as chord1.
        //
        //   Armed (tool letter held):
        //     - each cycle dir: bridge appends a vector step; other
        //       directional buildings record facing.
        //     - tool letter released → commit.
        let prev_mask = self.chord.last_mask;
        if keys.mask != 0 {
            self.chord.max_mask |= keys.mask;
        }
        let hjkl_cycle_ended = prev_mask != 0 && keys.mask == 0;
        let hjkl_cycle_dir = if hjkl_cycle_ended {
            direction_from_mask(self.chord.max_mask)
        } else {
            None
        };
        if hjkl_cycle_ended {
            self.chord.max_mask = 0;
        }
        self.chord.last_mask = keys.mask;

        // Unified cycle direction: hjkl release OR numpad press, both
        // identically a "single chord cycle" pulse this frame.
        let cycle_dir = hjkl_cycle_dir.or(keys.digit_dir);

        if self.chord.armed.is_none() {
            // Idle. Tool press arms; otherwise cycle dir → primary.
            if let Some((tool_key, tool)) = keys.tool {
                // chord1 = held hjkl mask OR same-frame numpad press.
                let target_dir = direction_from_mask(self.chord.max_mask).or(keys.digit_dir);
                if let Some(target_dir) = target_dir {
                    self.chord.armed = Some(ArmedState {
                        tool,
                        tool_key,
                        target_dir,
                        facing: None,
                        bridge_vector: (0, 0),
                    });
                    // Consume chord1 so it isn't replayed as facing.
                    self.chord.max_mask = 0;
                } else {
                    self.last_event = Some(format!(
                        "{tool:?}: hold a direction (hjkl/;) or tap numpad first"
                    ));
                }
            } else if let Some(dir) = cycle_dir {
                self.dir_key(dir);
            }
        } else {
            // Armed. Collect inputs until tool letter is released.
            let extra_dir = cycle_dir;
            if let Some(dir) = extra_dir
                && let Some(armed) = self.chord.armed.as_mut()
            {
                if matches!(armed.tool, Pending::BuildBridge) {
                    let (dx, dy) = dir_delta(dir);
                    armed.bridge_vector.0 += dx;
                    armed.bridge_vector.1 += dy;
                } else {
                    armed.facing = Some(dir);
                }
            }
            if !keys.armed_tool_held
                && let Some(armed) = self.chord.armed.take()
            {
                self.commit_armed(&armed);
                self.chord.max_mask = 0;
            }
        }

        if keys.backspace {
            self.undo_last();
        }
        if keys.esc {
            self.chord.armed = None;
            self.chord.max_mask = 0;
            self.selected = None;
        }
        if keys.up {
            self.move_selection_lane(-1);
        }
        if keys.down {
            self.move_selection_lane(1);
        }
        if keys.space {
            <Self as titan_core::Playback>::step_forward(self, 1);
        }

        egui::Panel::left("opening-resources")
            .resizable(true)
            .default_size(180.0)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| {
                self.render_left_panel(ui);
            });

        egui::Panel::right("opening-sidebar")
            .resizable(true)
            .default_size(280.0)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| {
                self.render_sidebar(ui);
            });

        // The playback panel renders its own bottom panel (64px); the
        // tree panel sits ABOVE it (added next so egui carves above
        // the already-carved playback strip). X-axis is shared so the
        // tree's turn columns align with the progress bar.
        titan_core::render_playback_panel(ui, self, |_ui| {});
        egui::Panel::bottom("opening-tree")
            .resizable(true)
            .default_size(160.0)
            .min_size(80.0)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| {
                self.render_tree(ui);
            });

        egui::CentralPanel::default().show_inside(ui, |ui| {
            self.render_map(ui);
        });

        // Overlays: action wheel and marker prompt. Rendered last so
        // they sit over the map and consume input before propagation.
        if self.wheel.is_some() {
            self.render_wheel(ui);
        }
        if self.marker_prompt.is_some() {
            self.render_marker_prompt(ui);
        }
        if self.overwrite_prompt.is_some() {
            self.render_overwrite_prompt(ui);
        }
    }
}

impl App {
    /// Left panel: player's current resource stockpile and the
    /// per-building scaled cost table. Order mirrors the replay
    /// viewer's stats panel for consistency.
    fn render_left_panel(&mut self, ui: &mut egui::Ui) {
        use libre_engine::common::Team;
        use libre_engine::common::game_constants as gc;

        let p = &self.sim.game.players[0];
        let ti = p.titanium;
        let ax = p.axionite;

        ui.heading("Resources");
        ui.separator();
        egui::Grid::new("opening-resources-grid")
            .num_columns(2)
            .min_col_width(60.0)
            .show(ui, |ui| {
                ui.label("Ti");
                ui.monospace(format!("{ti}"));
                ui.end_row();
                ui.label("Ax");
                ui.monospace(format!("{ax}"));
                ui.end_row();
            });

        ui.add_space(8.0);
        ui.heading("Costs");
        ui.label(egui::RichText::new("scaled to current state").weak());
        ui.separator();
        // Order: builder, road, barrier, conveyor, armoured conveyor,
        // bridge, splitter, harvester, foundry, gunner, sentinel,
        // breach, launcher. Same as the replay's stats panel.
        let rows: &[(&str, (i32, i32))] = &[
            ("Builder", gc::BUILDER_BOT_BASE_COST),
            ("Road", gc::ROAD_BASE_COST),
            ("Barrier", gc::BARRIER_BASE_COST),
            ("Conveyor", gc::CONVEYOR_BASE_COST),
            ("ArmConv", gc::ARMOURED_CONVEYOR_BASE_COST),
            ("Bridge", gc::BRIDGE_BASE_COST),
            ("Splitter", gc::SPLITTER_BASE_COST),
            ("Harvester", gc::HARVESTER_BASE_COST),
            ("Foundry", gc::FOUNDRY_BASE_COST),
            ("Gunner", gc::GUNNER_BASE_COST),
            ("Sentinel", gc::SENTINEL_BASE_COST),
            ("Breach", gc::BREACH_BASE_COST),
            ("Launcher", gc::LAUNCHER_BASE_COST),
        ];
        egui::Grid::new("opening-costs-grid")
            .num_columns(3)
            .min_col_width(40.0)
            .show(ui, |ui| {
                ui.label("");
                ui.label(egui::RichText::new("Ti").weak());
                ui.label(egui::RichText::new("Ax").weak());
                ui.end_row();
                for (name, base) in rows {
                    let (sti, sax) = self.sim.game.scaled_cost(Team::A, *base);
                    ui.label(*name);
                    ui.monospace(format!("{sti}"));
                    ui.monospace(if sax == 0 {
                        String::new()
                    } else {
                        format!("{sax}")
                    });
                    ui.end_row();
                }
            });
    }

    fn render_sidebar(&mut self, ui: &mut egui::Ui) {
        ui.heading("opening");
        ui.label(
            self.map_path
                .file_name()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default(),
        );
        ui.separator();

        // ── Status block ──────────────────────────────────────────
        // Always-on. Everything the keyboard handler reads from
        // hidden state — turn position, selection, chord direction,
        // and the most recent event. Resources and costs live in the
        // dedicated left panel.
        let edit_turn = self.edit_turn;
        let horizon = self.opening.horizon;
        let chord_dir = direction_from_mask(self.chord.max_mask);
        let chord_mask = self.chord.max_mask;
        let armed_text: Option<String> = self.chord.armed.as_ref().map(|a| {
            let target = name_for(a.target_dir);
            if matches!(a.tool, Pending::BuildBridge) {
                format!(
                    "armed {:?}: source {target}, vector ({:+},{:+})",
                    a.tool, a.bridge_vector.0, a.bridge_vector.1
                )
            } else {
                let facing = a.facing.map_or_else(
                    || format!("{target} (default)"),
                    |d| name_for(d).to_string(),
                );
                format!("armed {:?}: target {target}, facing {facing}", a.tool)
            }
        });
        let selection_text = match self.selected {
            Some(id) => format!("► {}", unit_label(&self.sim, &self.opening, id)),
            None => "► (no unit — click map / tree or use ↑/↓)".to_string(),
        };
        let last_event = self.last_event.clone();

        let mut horizon_delta: i32 = 0;
        egui::Frame::new()
            .fill(ui.visuals().faint_bg_color)
            .inner_margin(egui::Margin::same(6))
            .corner_radius(4.0)
            .show(ui, |ui| {
                ui.label(egui::RichText::new(selection_text).strong());

                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("turn T{edit_turn} / horizon {horizon}"))
                            .strong(),
                    );
                    if ui.small_button("-").clickable().clicked() {
                        horizon_delta = -1;
                    }
                    if ui.small_button("+").clickable().clicked() {
                        horizon_delta = 1;
                    }
                });

                let chord_text = match chord_dir {
                    Some(d) => format!("chord: {}  ({})", arrow_for(d), name_for(d)),
                    None if chord_mask != 0 => {
                        format!("chord: (cancel — opposite keys: {chord_mask:05b})")
                    }
                    None => "chord: —  (hold hjkl/; then tap tool letter)".to_string(),
                };
                ui.colored_label(
                    if chord_dir.is_some() {
                        titan_core::style::COLOR_INFO
                    } else {
                        ui.visuals().weak_text_color()
                    },
                    chord_text,
                );

                if let Some(text) = &armed_text {
                    ui.colored_label(titan_core::style::COLOR_INFO, text);
                }

                if let Some(ev) = &last_event {
                    ui.label(egui::RichText::new(format!("last: {ev}")).italics());
                } else {
                    ui.label(egui::RichText::new("last: —").weak());
                }
            });
        if horizon_delta < 0 && self.opening.horizon > 1 {
            self.opening.horizon -= 1;
            truncate_to_horizon(&mut self.opening);
            if self.edit_turn >= self.opening.horizon {
                self.edit_turn = self.opening.horizon - 1;
            }
            self.refresh_sim();
        } else if horizon_delta > 0 {
            self.opening.horizon += 1;
            extend_to_horizon(&mut self.opening);
            self.refresh_sim();
        }
        ui.separator();

        // Action queue display. Read-only except for ✕ delete.
        // All authoring is keyboard-driven via the chord scheme; the
        // sidebar is just a window into the opening's per-turn slots.
        if let Some(id) = self.selected
            && let Some(&opening_id) = self.sim.engine_to_opening.get(&id) {
                let turn = self.edit_turn;
                if turn < self.opening.horizon {
                    titan_core::style::section_title(ui, &format!("actions @ T{turn}"));
                    let queue: Vec<(usize, String)> = self
                        .opening
                        .actions(opening_id, turn)
                        .iter()
                        .enumerate()
                        .map(|(i, a)| (i, a.label()))
                        .collect();
                    if queue.is_empty() {
                        ui.label(egui::RichText::new("(empty)").weak());
                    }
                    let mut delete_idx: Option<usize> = None;
                    for (i, label) in queue {
                        if ui
                            .selectable_label(false, format!("{i}. {label}  ✕"))
                            .clickable()
                            .clicked()
                        {
                            delete_idx = Some(i);
                        }
                    }
                    if let Some(idx) = delete_idx {
                        let snapshot = self.opening.clone();
                        if self.opening.remove_action(opening_id, turn, idx) {
                            self.undo_stack.push(UndoEntry {
                                before: snapshot,
                                label: format!("delete T{turn}[{idx}]"),
                            });
                            self.opening.ensure_unit_tree();
                            self.refresh_sim();
                            self.last_event = Some(format!("deleted T{turn}[{idx}]"));
                        }
                    }
                }
            }
        ui.separator();

        titan_core::style::section_title(ui, "spawn order");
        let units: Vec<i32> = self
            .sim
            .turn_units
            .iter()
            .copied()
            .filter(|uid| self.sim.engine_to_opening.contains_key(uid))
            .collect();
        let mut to_select: Option<i32> = None;
        for uid in units {
            let label = unit_label(&self.sim, &self.opening, uid);
            let selected = self.selected == Some(uid);
            if ui.selectable_label(selected, label).clickable().clicked() {
                to_select = Some(uid);
            }
        }
        if let Some(uid) = to_select {
            self.select_unit(uid);
        }
        ui.separator();

        ui.add_space(8.0);
        if ui.button("Export Python…").clickable().clicked() {
            let py_path = self
                .opening_path
                .clone()
                .unwrap_or_else(|| self.map_path.with_extension("opening"))
                .with_extension("py");
            match crate::export::write_python(&self.opening, &py_path) {
                Ok(()) => {
                    self.last_event = Some(format!("exported {}", py_path.display()));
                }
                Err(e) => self.last_event = Some(format!("export: {e}")),
            }
        }

        ui.add_space(4.0);
        ui.checkbox(&mut self.show_unit_ids, "Show IDs on map")
            .clickable();

        ui.add_space(4.0);
        titan_core::style::section_title(ui, "controls");
        ui.small("Space          step turn forward");
        ui.small("←  →           ±1 turn   (Shift = ±10)");
        ui.small("↑ / ↓          previous / next unit lane");
        ui.small("Esc / RMB      deselect / cancel armed build");
        ui.small("Backspace / Ctrl+Z   undo last queued action");
        ui.small("");
        ui.small("Direction (chord — hold simultaneously):");
        ui.small("    k          N");
        ui.small("  h   l      W   E");
        ui.small("    j          S       ;  centre (own tile)");
        ui.small("  pairs:  hk=NW  kl=NE  jl=SE  hj=SW");
        ui.small("");
        ui.small("Bare release of hjkl → primary action:");
        ui.small("  Builder = Move   Core = Spawn");
        ui.small("  Turret  = Rotate");
        ui.small("");
        ui.small("Hold tool letter to arm a build. Tool tap");
        ui.small("captures chord1 as target; while tool is held:");
        ui.small("  • directional building: next chord = facing");
        ui.small("  • bridge: each chord cycle = +1 vector step");
        ui.small("  • numpad digit: same as a chord cycle");
        ui.small("Release the tool letter to commit.");
        ui.small("");
        ui.small("Tool letters:");
        ui.small("  c Conveyor   a ArmConv   s Splitter");
        ui.small("  b Bridge     v Harvester r Road");
        ui.small("  w Barrier    g Gunner    t Sentinel");
        ui.small("  x Breach     e Launcher  f Foundry");
        ui.small("  d Destroy");
        ui.small("");
        ui.small("Numpad 1–9     direct 8-way primary action");
        ui.small("Numpad 5       centre (own tile / no step)");
        ui.small("");
        ui.small("Map:");
        ui.small("  LMB drag    pan");
        ui.small("  wheel       zoom");
        ui.small("  LMB tile    select unit");
        ui.small("  RMB         deselect");
    }

    /// Tree-view panel: x-axis = turn (synced with the progress
    /// bar), y-axis = unit lane (one row per opening unit, in BFS
    /// order from the core down). Each unit's lifetime is a
    /// horizontal bar. A vertical drop from parent's row to a
    /// child's row at the child's `spawn_turn` shows the
    /// creating-action edge.
    ///
    /// Click anywhere in the panel to seek `edit_turn` to that x AND
    /// select the unit at that y. Dragging extends seek/select
    /// continuously.
    fn render_tree(&mut self, ui: &mut egui::Ui) {
        let lanes = unit_lanes(&self.opening);
        let horizon = self.opening.horizon.max(1);
        let avail = ui.available_size();
        let (response, painter) = ui.allocate_painter(avail, egui::Sense::click_and_drag());
        let rect = response.rect;
        painter.rect_filled(rect, 0.0, ui.visuals().extreme_bg_color);
        if response.hovered() {
            ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
        }

        // Layout: leave a left gutter for unit labels, use the rest
        // for the x-axis (turn 0..horizon) and y-axis (unit lanes).
        const GUTTER_W: f32 = 92.0;
        const ROW_PADDING_Y: f32 = 4.0;
        let plot_x0 = rect.left() + GUTTER_W;
        let plot_x1 = rect.right() - 4.0;
        let plot_w = (plot_x1 - plot_x0).max(1.0);
        let row_h = if lanes.is_empty() {
            16.0
        } else {
            (2.0f32.mul_add(-ROW_PADDING_Y, rect.height()) / lanes.len() as f32).clamp(14.0, 28.0)
        };

        // Click / drag: convert pointer to (turn, lane), seek+select.
        if (response.clicked() || response.dragged())
            && let Some(p) = response.interact_pointer_pos() {
                let frac = ((p.x - plot_x0) / plot_w).clamp(0.0, 1.0);
                let target_turn = (frac * horizon as f32) as usize;
                let last = self.opening.horizon.saturating_sub(1);
                self.edit_turn = target_turn.min(last);
                self.refresh_sim();

                if !lanes.is_empty() {
                    let lane_top = rect.top() + ROW_PADDING_Y;
                    let lane = (((p.y - lane_top) / row_h).floor() as i32)
                        .clamp(0, lanes.len() as i32 - 1) as usize;
                    let target_oid = lanes[lane];
                    let engine_id = self
                        .sim
                        .engine_to_opening
                        .iter()
                        .find(|&(_, &oid)| oid == target_oid)
                        .map(|(&eid, _)| eid);
                    match engine_id {
                        Some(eid) => self.select_unit(eid),
                        None => self.select_opening_id_latent(target_oid),
                    }
                }
            }

        // X-axis ticks (every 5 turns).
        let tick_color = ui.visuals().weak_text_color();
        for t in (0..=horizon).step_by(5) {
            let x = plot_x0 + plot_w * (t as f32 / horizon as f32);
            painter.line_segment(
                [egui::pos2(x, rect.top()), egui::pos2(x, rect.bottom())],
                egui::Stroke::new(1.0, tick_color.gamma_multiply(0.3)),
            );
            painter.text(
                egui::pos2(x + 2.0, rect.top() + 2.0),
                egui::Align2::LEFT_TOP,
                format!("{t}"),
                egui::FontId::monospace(10.0),
                tick_color,
            );
        }

        // edit_turn cursor line.
        let cursor_x = plot_x0 + plot_w * (self.edit_turn as f32 / horizon as f32);
        painter.line_segment(
            [
                egui::pos2(cursor_x, rect.top()),
                egui::pos2(cursor_x, rect.bottom()),
            ],
            egui::Stroke::new(2.0, titan_core::style::COLOR_INFO),
        );

        // Selected opening_id (for highlighting the lane's bar).
        let selected_oid = self
            .selected
            .and_then(|uid| self.sim.engine_to_opening.get(&uid).copied());

        // Lane index lookup for parent-row.
        let lane_idx: std::collections::HashMap<u32, usize> = lanes
            .iter()
            .copied()
            .enumerate()
            .map(|(i, id)| (id, i))
            .collect();

        for (i, &oid) in lanes.iter().enumerate() {
            let Some(plan) = self.opening.team.units.get(&oid) else {
                continue;
            };
            let lane_y = (i as f32 + 0.5).mul_add(row_h, rect.top() + ROW_PADDING_Y);
            let bar_y0 = lane_y - row_h * 0.32;
            let bar_y1 = lane_y + row_h * 0.32;
            let x0 = plot_x0 + plot_w * (plan.spawn_turn as f32 / horizon as f32);
            let x1 = plot_x1;
            let kind_color = kind_color(plan.kind);
            let highlight = Some(oid) == selected_oid;
            let bar_color = if highlight {
                kind_color.gamma_multiply(1.4)
            } else {
                kind_color.gamma_multiply(0.8)
            };
            painter.rect_filled(
                egui::Rect::from_min_max(egui::pos2(x0, bar_y0), egui::pos2(x1, bar_y1)),
                2.0,
                bar_color,
            );
            if highlight {
                painter.rect_stroke(
                    egui::Rect::from_min_max(egui::pos2(x0, bar_y0), egui::pos2(x1, bar_y1)),
                    2.0,
                    egui::Stroke::new(1.5, SELECTION_STROKE),
                    egui::StrokeKind::Outside,
                );
            }

            // Label in the gutter — kind plus birth-turn suffix.
            // Cores get no suffix (always one, always at T0).
            let label = if oid == crate::opening::CORE_OPENING_ID {
                plan.kind.label().to_string()
            } else {
                format!("{} T{}", plan.kind.label(), plan.spawn_turn)
            };
            painter.text(
                egui::pos2(plot_x0 - 4.0, lane_y),
                egui::Align2::RIGHT_CENTER,
                label,
                egui::FontId::monospace(11.0),
                ui.visuals().text_color(),
            );

            // Edge from parent row down to this row at spawn_turn.
            if let Some(parent_id) = plan.parent
                && let Some(&parent_lane) = lane_idx.get(&parent_id)
            {
                let parent_y = (parent_lane as f32 + 0.5).mul_add(row_h, rect.top() + ROW_PADDING_Y);
                painter.line_segment(
                    [egui::pos2(x0, parent_y), egui::pos2(x0, lane_y)],
                    egui::Stroke::new(1.5, kind_color.gamma_multiply(0.6)),
                );
            }

            // Tick marks for turns where this unit has queued actions.
            for (rel, slot) in plan.actions.iter().enumerate() {
                if slot.items.is_empty() {
                    continue;
                }
                let t = plan.spawn_turn + rel;
                let tx = plot_x0 + plot_w * (t as f32 / horizon as f32);
                painter.line_segment(
                    [egui::pos2(tx, bar_y0), egui::pos2(tx, bar_y1)],
                    egui::Stroke::new(1.5, egui::Color32::WHITE),
                );
            }
        }
    }

    /// Radial action wheel overlay. Rendered as a top-level area at
    /// the wheel's centre. Each wedge is a clickable button; centre
    /// is "cancel". After a pick we call `commit_wheel_choice`.
    fn render_wheel(&mut self, ui: &mut egui::Ui) {
        let Some(wheel) = self.wheel.clone() else {
            return;
        };
        let n = wheel.options.len() as f32;
        if n == 0.0 {
            self.wheel = None;
            return;
        }

        let mut chosen: Option<Pending> = None;
        let mut cancel = false;

        // Sized so 14 wedges fit cleanly: at mid-radius=150 the
        // per-wedge arc is 2π·150/14 ≈ 67px, wider than the 60px
        // hitbox so adjacent icons don't visually touch.
        let outer = 220.0_f32;
        let inner = 80.0_f32;
        let mid = (outer + inner) * 0.5;
        let wedge = 60.0_f32;
        let icon = 52.0_f32;

        egui::Area::new(egui::Id::new("opening-wheel"))
            .order(egui::Order::Foreground)
            .fixed_pos(egui::pos2(wheel.centre.x - outer, wheel.centre.y - outer))
            .show(ui.ctx(), |ui| {
                let painter = ui.painter();
                let centre = egui::pos2(wheel.centre.x, wheel.centre.y);

                // Backdrop disk.
                painter.circle_filled(centre, outer + 6.0, egui::Color32::from_black_alpha(190));

                // Centre cancel.
                let cancel_rect =
                    egui::Rect::from_center_size(centre, egui::Vec2::splat(inner * 1.4));
                let cancel_resp = ui
                    .interact(
                        cancel_rect,
                        egui::Id::new("wheel-cancel"),
                        egui::Sense::click(),
                    )
                    .on_hover_cursor(egui::CursorIcon::PointingHand);
                let cancel_bg = if cancel_resp.hovered() {
                    egui::Color32::from_rgb(0x60, 0x40, 0x40)
                } else {
                    egui::Color32::from_rgb(0x40, 0x40, 0x40)
                };
                painter.circle_filled(centre, inner * 0.7, cancel_bg);
                painter.text(
                    centre,
                    egui::Align2::CENTER_CENTER,
                    "✕",
                    egui::FontId::proportional(20.0),
                    egui::Color32::WHITE,
                );
                if cancel_resp.clicked() {
                    cancel = true;
                }

                // Wedges. Each option goes at angle (i/n) of full
                // turn, starting at the top (-π/2). Sprite icon
                // pulled from the atlas; falls back to text when
                // the action has no clean visual.
                for (i, option) in wheel.options.iter().enumerate() {
                    let angle =
                        std::f32::consts::TAU.mul_add(i as f32 / n, -std::f32::consts::FRAC_PI_2);
                    let p = egui::pos2(angle.cos().mul_add(mid, centre.x), angle.sin().mul_add(mid, centre.y));
                    let hit_rect = egui::Rect::from_center_size(p, egui::Vec2::splat(wedge));
                    let resp = ui
                        .interact(
                            hit_rect,
                            egui::Id::new(("wheel-wedge", i)),
                            egui::Sense::click(),
                        )
                        .on_hover_cursor(egui::CursorIcon::PointingHand);
                    // No persistent fill — just a faint hover glow
                    // around the icon when the cursor is on it.
                    if resp.hovered() {
                        painter.rect_filled(hit_rect, 8.0, egui::Color32::from_white_alpha(0x18));
                    }

                    // Icon (top of cell) + label (bottom).
                    let icon_rect = egui::Rect::from_center_size(
                        egui::pos2(p.x, p.y - 6.0),
                        egui::Vec2::splat(icon),
                    );
                    let label_pos = egui::pos2(p.x, icon.mul_add(0.5, p.y));
                    if let Some(name) = pending_sprite(*option)
                        && let Some(tex) = self.atlas.get(name)
                    {
                        painter.image(
                            tex,
                            icon_rect,
                            egui::Rect::from_min_max(egui::Pos2::ZERO, egui::Pos2::new(1.0, 1.0)),
                            egui::Color32::WHITE,
                        );
                    } else {
                        painter.text(
                            icon_rect.center(),
                            egui::Align2::CENTER_CENTER,
                            "✕",
                            egui::FontId::proportional(20.0),
                            egui::Color32::from_rgb(0xff, 0x80, 0x80),
                        );
                    }
                    painter.text(
                        label_pos,
                        egui::Align2::CENTER_CENTER,
                        option.label(),
                        egui::FontId::proportional(10.0),
                        egui::Color32::WHITE,
                    );
                    if resp.clicked() {
                        chosen = Some(*option);
                    }
                }
            });

        if cancel {
            self.wheel = None;
            self.last_event = Some("wheel: cancelled".into());
        } else if let Some(p) = chosen {
            self.commit_wheel_choice(p);
        }

        // Esc also cancels.
        if ui.ctx().input(|i| i.key_pressed(egui::Key::Escape)) {
            self.wheel = None;
        }
    }

    /// Modal text input for marker value. Accepts decimal, `0x...`,
    /// `0b...`. Submit with Enter; cancel with Esc.
    fn render_marker_prompt(&mut self, ui: &mut egui::Ui) {
        let Some(mut prompt) = self.marker_prompt.clone() else {
            return;
        };
        let mut close: Option<Result<u32, String>> = None;
        egui::Modal::new(egui::Id::new("marker-modal")).show(ui.ctx(), |ui| {
            ui.heading("Marker value");
            ui.label(format!("at ({}, {})", prompt.target.0, prompt.target.1));
            ui.label(egui::RichText::new("decimal, 0x… (hex), or 0b… (bin)").weak());
            let resp = ui.text_edit_singleline(&mut prompt.buffer);
            resp.request_focus();

            ui.horizontal(|ui| {
                if ui.button("OK").clicked() || ui.ctx().input(|i| i.key_pressed(egui::Key::Enter))
                {
                    close = Some(parse_marker_value(&prompt.buffer));
                }
                if ui.button("Cancel").clicked()
                    || ui.ctx().input(|i| i.key_pressed(egui::Key::Escape))
                {
                    close = Some(Err("cancelled".into()));
                }
            });
        });
        match close {
            Some(Ok(value)) => {
                let opening_id = self.sim.engine_to_opening.get(&prompt.uid).copied();
                if let Some(opening_id) = opening_id {
                    self.append_tracked(
                        opening_id,
                        self.edit_turn,
                        crate::opening::Action::PlaceMarker {
                            x: prompt.target.0,
                            y: prompt.target.1,
                            value,
                        },
                    );
                }
                self.marker_prompt = None;
            }
            Some(Err(reason)) => {
                if reason == "cancelled" {
                    self.marker_prompt = None;
                } else {
                    self.last_event = Some(format!("marker: {reason}"));
                    self.marker_prompt = Some(prompt);
                }
            }
            None => {
                self.marker_prompt = Some(prompt);
            }
        }
    }

    /// Modal: confirm before overwriting an existing `.opening` file.
    /// Triggered by `save_file` when the target exists and isn't the
    /// path we loaded from. Overwrite proceeds via `force_save_to`.
    fn render_overwrite_prompt(&mut self, ui: &mut egui::Ui) {
        let Some(path) = self.overwrite_prompt.clone() else {
            return;
        };
        enum Action {
            Overwrite,
            Cancel,
        }
        let mut action: Option<Action> = None;
        egui::Modal::new(egui::Id::new("overwrite-modal")).show(ui.ctx(), |ui| {
            ui.heading("File exists");
            ui.label(format!("{}", path.display()));
            ui.label(egui::RichText::new("This file already exists. Overwrite?").strong());
            ui.horizontal(|ui| {
                if ui.button("Overwrite").clicked() {
                    action = Some(Action::Overwrite);
                }
                if ui.button("Cancel").clicked()
                    || ui.ctx().input(|i| i.key_pressed(egui::Key::Escape))
                {
                    action = Some(Action::Cancel);
                }
            });
        });
        match action {
            Some(Action::Overwrite) => {
                self.overwrite_prompt = None;
                self.force_save_to(path);
            }
            Some(Action::Cancel) => {
                self.overwrite_prompt = None;
                self.last_event = Some("save: cancelled".into());
            }
            None => {}
        }
    }

    fn render_map(&mut self, ui: &mut egui::Ui) {
        let (response, painter) =
            ui.allocate_painter(ui.available_size(), egui::Sense::click_and_drag());
        let rect = response.rect;
        let ts = self.atlas.tile_size;
        painter.rect_filled(rect, 0.0, BG_COLOR);

        if response.dragged_by(egui::PointerButton::Primary) {
            self.pan += response.drag_delta();
            ui.ctx().set_cursor_icon(egui::CursorIcon::Grabbing);
        }

        let scroll = ui.ctx().input(|i| i.smooth_scroll_delta.y);
        if scroll != 0.0 && response.hovered() {
            let factor = (scroll * 0.01).exp();
            if let Some(mouse) = ui.ctx().input(|i| i.pointer.hover_pos()) {
                let old_origin = egui::Pos2::new(rect.left() + self.pan.x, rect.top() + self.pan.y);
                let new_zoom = (self.zoom * factor).clamp(MIN_ZOOM, 8.0);
                let local = mouse - old_origin;
                let scale = new_zoom / self.zoom;
                let new_origin = mouse - local * scale;
                self.pan = egui::Vec2::new(new_origin.x - rect.left(), new_origin.y - rect.top());
                self.zoom = new_zoom;
            }
        }

        let w = self.map.width;
        let h = self.map.height;
        self.pan = clamp_pan(self.pan, rect, w, h, ts, self.zoom, 64.0);
        let origin = egui::Pos2::new(rect.left() + self.pan.x, rect.top() + self.pan.y);

        // Whole map is clickable: pointer cursor + tile highlight.
        let mut hovered_tile: Option<(i32, i32)> = None;
        if response.hovered()
            && let Some(pos) = ui.ctx().input(|i| i.pointer.hover_pos())
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            if gx >= 0 && gx < w && gy >= 0 && gy < h {
                hovered_tile = Some((gx, gy));
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }
        }

        // Modifier state for shift+RMB / shift+MMB.
        let shift = ui.ctx().input(|i| i.modifiers.shift);

        // RMB on a tile.
        //   - Bridge picker active: this RMB sets the bridge target.
        //   - Wheel open: clicking outside the wheel cancels (handled
        //     in render_wheel; here we do nothing extra).
        //   - Selected unit + tile in action range: open action wheel.
        //   - Otherwise: cancel any in-flight pick / clear selection.
        if response.clicked_by(egui::PointerButton::Secondary)
            && let Some(pos) = response.interact_pointer_pos()
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            if shift {
                self.handle_shift_rmb(gx, gy);
            } else if let Some(bp) = self.bridge_pending.clone() {
                self.commit_bridge(bp, gx, gy);
                self.bridge_pending = None;
            } else if self.wheel.is_some() {
                // Cancellation: outside-the-wheel click.
                self.wheel = None;
            } else if self.marker_prompt.is_some() {
                self.marker_prompt = None;
            } else {
                self.try_open_wheel(gx, gy, pos);
            }
        }

        // Shift+MMB on a building tile: queue Destroy for that tile.
        // (Engine: free, unlimited per turn.)
        if response.clicked_by(egui::PointerButton::Middle)
            && shift
            && let Some(pos) = response.interact_pointer_pos()
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            self.queue_destroy_at(gx, gy);
        }

        // MMB click on a queued action's tile: rotate its facing.
        if response.clicked_by(egui::PointerButton::Middle)
            && !shift
            && let Some(pos) = response.interact_pointer_pos()
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            self.rotate_queued_at(gx, gy);
        }

        // LMB tile click selects whatever's there.
        if response.clicked_by(egui::PointerButton::Primary)
            && let Some(pos) = response.interact_pointer_pos()
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            if let Some(uid) = self.entity_at(gx, gy) {
                self.select_unit(uid);
            } else {
                self.selected = None;
            }
        }

        let origin_vec = egui::Vec2::new(origin.x, origin.y);
        #[allow(clippy::float_cmp)]
        if origin_vec != self.cached_map_origin || self.zoom != self.cached_map_zoom {
            self.cached_map_shapes = titan_core::map::build_static_map_shapes(
                &self.atlas,
                w,
                h,
                self.zoom,
                origin,
                |x, y| self.map_env(x, y),
            );
            self.cached_map_origin = origin_vec;
            self.cached_map_zoom = self.zoom;
        }
        painter.extend(self.cached_map_shapes.clone());

        render_entities(
            &painter,
            &self.atlas,
            &self.sim.game,
            ts,
            origin,
            self.zoom,
            self.show_unit_ids,
        );

        // Per-turn diff overlay: dirtied tiles (placed/destroyed) and
        // builder movement arrows. Tells the user what their currently
        // authored turn does at a glance.
        if let Some(diff) = self.turn_diff.clone() {
            let dirty_stroke = egui::Stroke::new(2.0, egui::Color32::from_rgb(0xff, 0xc0, 0x40));
            for &(dx, dy) in &diff.dirtied {
                if dx >= 0 && dx < w && dy >= 0 && dy < h {
                    let r = tile_rect(dx, dy, ts, origin, self.zoom);
                    painter.rect_stroke(r, 2.0, dirty_stroke, egui::StrokeKind::Inside);
                }
            }
            let arrow_color = egui::Color32::from_rgb(0x40, 0xc0, 0xff);
            let arrow_stroke = egui::Stroke::new(2.5, arrow_color);
            for &(from, to) in &diff.moves {
                let p0 = titan_core::tile::tile_center(from.0, from.1, ts, origin, self.zoom);
                let p1 = titan_core::tile::tile_center(to.0, to.1, ts, origin, self.zoom);
                painter.line_segment([p0, p1], arrow_stroke);
                // Arrowhead at p1.
                let dir = (p1 - p0).normalized();
                let perp = egui::Vec2::new(-dir.y, dir.x);
                let head = ts * self.zoom * 0.25;
                let tip = p1;
                let l = tip - dir * head + perp * head * 0.6;
                let r = tip - dir * head - perp * head * 0.6;
                painter.add(egui::Shape::convex_polygon(
                    vec![tip, l, r],
                    arrow_color,
                    egui::Stroke::NONE,
                ));
            }
        }

        // Selection highlight. Latent rule: if the selected unit's
        // opening lifetime hasn't started yet at this `edit_turn`,
        // draw nothing on the map. Selection persists in state so it
        // re-resolves once time advances past `spawn_turn`.
        if let Some(id) = self.selected
            && let Some(e) = self.sim.game.entities.get(&id)
            && self.sim.engine_to_opening.get(&id).is_some_and(|&oid| {
                self.opening
                    .team
                    .units
                    .get(&oid)
                    .is_some_and(|p| self.edit_turn >= p.spawn_turn)
            })
        {
            let p = e.position;
            let r = match e {
                libre_engine::game_map::Entity::Core(_) => egui::Rect::from_min_size(
                    tile_rect(p.x - 1, p.y - 1, ts, origin, self.zoom).min,
                    egui::Vec2::splat(ts * self.zoom * 3.0),
                ),
                _ => tile_rect(p.x, p.y, ts, origin, self.zoom),
            };
            painter.rect_stroke(
                r,
                0.0,
                egui::Stroke::new(2.0, SELECTION_STROKE),
                egui::StrokeKind::Outside,
            );
        }

        // Chord direction preview: highlight the tile one step from the
        // selected unit in the held direction. Tells the user exactly
        // what their next keypress will target.
        if let Some(dir) = direction_from_mask(self.chord.max_mask)
            && let Some(uid) = self.selected
            && let Some(e) = self.sim.game.entities.get(&uid)
        {
            let (dx, dy) = dir_delta(dir);
            let (tx, ty) = (e.position.x + dx, e.position.y + dy);
            if tx >= 0 && tx < w && ty >= 0 && ty < h {
                painter.rect_stroke(
                    tile_rect(tx, ty, ts, origin, self.zoom),
                    0.0,
                    egui::Stroke::new(
                        2.0,
                        egui::Color32::from_rgba_premultiplied(0x40, 0xc0, 0xff, 0xff),
                    ),
                    egui::StrokeKind::Outside,
                );
            }
        }

        // Hovered-tile highlight: show the user which tile their
        // next click would target.
        if let Some((hx, hy)) = hovered_tile {
            painter.rect_stroke(
                tile_rect(hx, hy, ts, origin, self.zoom),
                0.0,
                egui::Stroke::new(1.5, egui::Color32::from_rgb(0xff, 0xff, 0xff)),
                egui::StrokeKind::Inside,
            );
        }
    }
}

/// Atlas sprite name for a wheel wedge's icon. `None` for actions
/// that have no clean visual (Destroy). Player team is hard-coded
/// to `gold` (Team A); the editor authors only the player's plan.
const fn pending_sprite(p: Pending) -> Option<&'static str> {
    match p {
        Pending::BuildConveyor => Some("conveyor_gold_n"),
        Pending::BuildArmouredConveyor => Some("armoured_conveyor_gold_n"),
        Pending::BuildSplitter => Some("splitter_n_gold"),
        Pending::BuildBridge => Some("bridge_stand_gold"),
        Pending::BuildHarvester => Some("harvester_gold"),
        Pending::BuildFoundry => Some("foundry_gold"),
        Pending::BuildRoad => Some("road_gold"),
        Pending::BuildBarrier => Some("barrier_gold"),
        Pending::BuildGunner => Some("gunner_n_gold"),
        Pending::BuildSentinel => Some("sentinel_n_gold"),
        Pending::BuildBreach => Some("breach_n_gold"),
        Pending::BuildLauncher => Some("launcher_gold"),
        Pending::Marker => Some("marker_gold"),
        Pending::Spawn => Some("builderbot_front_gold"),
        Pending::Destroy => None,
    }
}

/// Parse a marker-value string. Accepts `0x…` (hex), `0b…` (bin),
/// or unprefixed decimal.
fn parse_marker_value(s: &str) -> Result<u32, String> {
    let s = s.trim();
    if let Some(hex) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        u32::from_str_radix(hex, 16).map_err(|e| format!("hex: {e}"))
    } else if let Some(bin) = s.strip_prefix("0b").or_else(|| s.strip_prefix("0B")) {
        u32::from_str_radix(bin, 2).map_err(|e| format!("bin: {e}"))
    } else if s.is_empty() {
        Err("empty".to_string())
    } else {
        s.parse::<u32>().map_err(|e| format!("dec: {e}"))
    }
}

/// What actions the wheel offers for this unit kind. Independent
/// of the click target — engine validates range at commit time.
///
/// - **Builder**: full build / destroy / marker set.
/// - **Core**: Spawn (own 3x3 only) and Marker (5x5 perimeter only).
/// - **Turret / Launcher**: Marker (8 neighbours).
fn wheel_options_for(e: &libre_engine::game_map::Entity) -> Vec<Pending> {
    use libre_engine::game_map::Entity;
    match e {
        Entity::BuilderBot(_) => vec![
            Pending::BuildConveyor,
            Pending::BuildArmouredConveyor,
            Pending::BuildSplitter,
            Pending::BuildBridge,
            Pending::BuildHarvester,
            Pending::BuildFoundry,
            Pending::BuildRoad,
            Pending::BuildBarrier,
            Pending::BuildGunner,
            Pending::BuildSentinel,
            Pending::BuildBreach,
            Pending::BuildLauncher,
            Pending::Destroy,
            Pending::Marker,
        ],
        Entity::Core(_) => vec![Pending::Spawn, Pending::Marker],
        Entity::Gunner(_) | Entity::Sentinel(_) | Entity::Breach(_) | Entity::Launcher(_) => {
            vec![Pending::Marker]
        }
        _ => vec![],
    }
}

/// Map a Pending tool to its `DirectionalAction` key for last-used
/// memory, or None if the tool has no `dir` field.
const fn directional_kind_for(p: Pending) -> Option<DirectionalAction> {
    match p {
        Pending::BuildConveyor => Some(DirectionalAction::Conveyor),
        Pending::BuildArmouredConveyor => Some(DirectionalAction::ArmConv),
        Pending::BuildSplitter => Some(DirectionalAction::Splitter),
        Pending::BuildGunner => Some(DirectionalAction::Gunner),
        Pending::BuildSentinel => Some(DirectionalAction::Sentinel),
        Pending::BuildBreach => Some(DirectionalAction::Breach),
        _ => None,
    }
}

/// True if a builder can stand on this entity (per Battlecode rules:
/// conveyors, armoured conveyors, splitters, bridges, roads, allied
/// core).
const fn is_walkable_building(e: &libre_engine::game_map::Entity) -> bool {
    use libre_engine::game_map::Entity;
    matches!(
        e,
        Entity::Conveyor(_)
            | Entity::ArmouredConveyor(_)
            | Entity::Splitter(_)
            | Entity::Bridge(_)
            | Entity::Road(_)
            | Entity::Core(_)
    )
}

/// 8-way direction encoding the displacement vector. Used by
/// shift+RMB to convert (dx,dy) into a Move direction.
const fn vec_to_dir((dx, dy): (i32, i32)) -> i32 {
    match (dx, dy) {
        (0, -1) => 0,
        (1, -1) => 1,
        (1, 0) => 2,
        (1, 1) => 3,
        (0, 1) => 4,
        (-1, 1) => 5,
        (-1, 0) => 6,
        (-1, -1) => 7,
        _ => 0,
    }
}

/// True if `action`'s tile-target equals (gx, gy). Used to find a
/// queued action under the cursor for MMB-rotate.
const fn action_target_at(a: &crate::opening::Action, gx: i32, gy: i32) -> bool {
    use crate::opening::Action;
    match a {
        Action::BuildConveyor { x, y, .. }
        | Action::BuildArmouredConveyor { x, y, .. }
        | Action::BuildSplitter { x, y, .. }
        | Action::BuildBridge { x, y, .. }
        | Action::BuildHarvester { x, y }
        | Action::BuildRoad { x, y }
        | Action::BuildBarrier { x, y }
        | Action::BuildGunner { x, y, .. }
        | Action::BuildSentinel { x, y, .. }
        | Action::BuildBreach { x, y, .. }
        | Action::BuildLauncher { x, y }
        | Action::BuildFoundry { x, y }
        | Action::Destroy { x, y }
        | Action::Heal { x, y }
        | Action::Attack { x, y }
        | Action::PlaceMarker { x, y, .. } => *x == gx && *y == gy,
        Action::Move { .. } | Action::Spawn { .. } | Action::Rotate { .. } => false,
    }
}

/// Cycle a directional action's `dir` clockwise to the next valid
/// step for that action kind. Conveyors / armoured conveyors /
/// splitters take cardinal directions only (game rule), so rotation
/// snaps through N→E→S→W; everything else cycles through all 8.
/// Returns the kind/dir for `last_used` update if rotated.
fn rotate_action_dir(a: &mut crate::opening::Action) -> Option<(DirectionalAction, i32)> {
    use crate::opening::Action;
    let next8 = |d: i32| (d + 1) % 8;
    // 0=N → 2=E → 4=S → 6=W → 0=N. Fall back to N if dir was diagonal.
    let next_cardinal = |d: i32| match d {
        0 => 2,
        2 => 4,
        4 => 6,
        6 => 0,
        _ => 0,
    };
    match a {
        Action::BuildConveyor { dir, .. } => {
            *dir = next_cardinal(*dir);
            Some((DirectionalAction::Conveyor, *dir))
        }
        Action::BuildArmouredConveyor { dir, .. } => {
            *dir = next_cardinal(*dir);
            Some((DirectionalAction::ArmConv, *dir))
        }
        Action::BuildSplitter { dir, .. } => {
            *dir = next_cardinal(*dir);
            Some((DirectionalAction::Splitter, *dir))
        }
        Action::BuildGunner { dir, .. } => {
            *dir = next8(*dir);
            Some((DirectionalAction::Gunner, *dir))
        }
        Action::BuildSentinel { dir, .. } => {
            *dir = next8(*dir);
            Some((DirectionalAction::Sentinel, *dir))
        }
        Action::BuildBreach { dir, .. } => {
            *dir = next8(*dir);
            Some((DirectionalAction::Breach, *dir))
        }
        Action::Spawn { dir } => {
            *dir = next8(*dir);
            Some((DirectionalAction::Spawn, *dir))
        }
        Action::Move { dir } => {
            *dir = next8(*dir);
            Some((DirectionalAction::Move, *dir))
        }
        _ => None,
    }
}

/// Colour for a unit's tree-panel bar by kind.
const fn kind_color(kind: crate::opening::UnitKind) -> egui::Color32 {
    use crate::opening::UnitKind;
    match kind {
        UnitKind::Core => egui::Color32::from_rgb(0xc0, 0xa0, 0x40),
        UnitKind::Builder => egui::Color32::from_rgb(0x40, 0x90, 0xff),
        UnitKind::Gunner => egui::Color32::from_rgb(0xff, 0x80, 0x40),
        UnitKind::Sentinel => egui::Color32::from_rgb(0xc0, 0x60, 0xff),
        UnitKind::Breach => egui::Color32::from_rgb(0xff, 0x40, 0x60),
        UnitKind::Launcher => egui::Color32::from_rgb(0x60, 0xd0, 0x80),
    }
}

/// Unit lanes for the tree panel and Up/Down navigation. Returns
/// opening IDs in BFS order rooted at the core: parent before its
/// children, siblings in (`spawn_turn`, `opening_id`) order. Stable as
/// long as ids don't get reused (sparse allocator guarantees this).
fn unit_lanes(opening: &Opening) -> Vec<u32> {
    let mut lanes = Vec::with_capacity(opening.team.units.len());
    let mut queue = std::collections::VecDeque::from([crate::opening::CORE_OPENING_ID]);
    while let Some(id) = queue.pop_front() {
        if !opening.team.units.contains_key(&id) {
            continue;
        }
        lanes.push(id);
        let mut children: Vec<u32> = opening
            .team
            .units
            .iter()
            .filter(|(_, p)| p.parent == Some(id))
            .map(|(&k, _)| k)
            .collect();
        children.sort_by_key(|&k| {
            let p = &opening.team.units[&k];
            (p.spawn_turn, k)
        });
        for c in children {
            queue.push_back(c);
        }
    }
    lanes
}

/// One-line description of a unit for sidebar lists. The numeric
/// suffix is the unit's *birth turn* (T<n>), not its internal
/// `opening_id` — `opening_ids` are sparse and meaningless to the user
/// (delete + readd jumps the id), whereas the birth turn is stable
/// and self-explanatory. The core has no suffix (it's always there).
fn unit_label(sim: &Sim, opening: &Opening, uid: i32) -> String {
    let Some(e) = sim.game.entities.get(&uid) else {
        return format!("uid {uid} (gone)");
    };
    let (x, y) = (e.position.x, e.position.y);
    let opening_id = sim.engine_to_opening.get(&uid).copied();
    let plan = opening_id.and_then(|oid| opening.team.units.get(&oid));
    let kind = plan.map_or_else(|| match e {
            libre_engine::game_map::Entity::Core(_) => "core".to_string(),
            libre_engine::game_map::Entity::BuilderBot(_) => "builder".to_string(),
            libre_engine::game_map::Entity::Gunner(_) => "gunner".to_string(),
            libre_engine::game_map::Entity::Sentinel(_) => "sentinel".to_string(),
            libre_engine::game_map::Entity::Breach(_) => "breach".to_string(),
            libre_engine::game_map::Entity::Launcher(_) => "launcher".to_string(),
            _ => format!("uid {uid}"),
        }, |p| p.kind.label().to_string());
    match (opening_id, plan) {
        (Some(0), _) => format!("{kind} ({x},{y})"),
        (Some(_), Some(p)) => format!("{kind} T{} ({x},{y})", p.spawn_turn),
        (Some(oid), None) => format!("{kind} #{oid} ({x},{y})"),
        (None, _) => format!("{kind} (enemy) ({x},{y})"),
    }
}

/// 8-way direction → printable arrow glyph. Used for the chord-state
/// preview at the top of the sidebar.
const fn arrow_for(dir: i32) -> &'static str {
    match dir {
        0 => "↑",
        1 => "↗",
        2 => "→",
        3 => "↘",
        4 => "↓",
        5 => "↙",
        6 => "←",
        7 => "↖",
        _ => "·",
    }
}

const fn name_for(dir: i32) -> &'static str {
    match dir {
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

/// 8-way direction → unit displacement vector. `8` is Centre (no
/// movement), used for "build on own tile". Inverse of `vec_to_dir`.
const fn dir_delta(dir: i32) -> (i32, i32) {
    match dir {
        0 => (0, -1),
        1 => (1, -1),
        2 => (1, 0),
        3 => (1, 1),
        4 => (0, 1),
        5 => (-1, 1),
        6 => (-1, 0),
        7 => (-1, -1),
        _ => (0, 0),
    }
}

/// Decode a held-key bitmask into a direction:
/// N=1 (k), E=2 (l), S=4 (j), W=8 (h), Centre=16 (`;`).
/// Opposite keys cancel; mixing Centre with anything else is invalid.
const fn direction_from_mask(mask: u8) -> Option<i32> {
    match mask {
        0b00001 => Some(0), // N
        0b00011 => Some(1), // NE
        0b00010 => Some(2), // E
        0b00110 => Some(3), // SE
        0b00100 => Some(4), // S
        0b01100 => Some(5), // SW
        0b01000 => Some(6), // W
        0b01001 => Some(7), // NW
        0b10000 => Some(8), // Centre
        _ => None,
    }
}

/// Truncate every unit's action vector to fit within the new horizon.
fn truncate_to_horizon(opening: &mut Opening) {
    let horizon = opening.horizon;
    for plan in opening.team.units.values_mut() {
        let max = horizon.saturating_sub(plan.spawn_turn);
        plan.actions.truncate(max);
    }
}

/// Append empty action queues so every unit covers the new horizon.
fn extend_to_horizon(opening: &mut Opening) {
    let horizon = opening.horizon;
    for plan in opening.team.units.values_mut() {
        let needed = horizon.saturating_sub(plan.spawn_turn);
        while plan.actions.len() < needed {
            plan.actions.push(crate::opening::TurnActions::default());
        }
    }
}
