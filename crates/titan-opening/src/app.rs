use std::path::{Path, PathBuf};
use std::sync::Arc;

use cambc_proto as proto;
use eframe::egui;
use prost::Message;
use titan_core::SpriteSet;
use titan_core::map::BG_COLOR;
use titan_core::tile::{MIN_ZOOM, clamp_pan, tile_rect};

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
    /// When set, the next map click sets the target of this action.
    pub pending: Option<Pending>,
    /// Overlay each unit's engine ID on its tile.
    pub show_unit_ids: bool,

    pub error: Option<String>,
}

/// Action template waiting for a target tile. The user clicks on the
/// map; the editor synthesises the full action with that tile as the
/// target, queues it on the selected unit's action list, and clears
/// `pending`. Direction (where applicable) is auto-derived as the cardinal
/// or 8-way direction from the unit to the click target.
#[derive(Clone, Copy, Debug)]
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
    Heal,
    Marker,
}

impl App {
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
            pending: None,
            show_unit_ids: true,
            error: None,
        };
        app.refresh_sim();
        app
    }

    /// Move selection to the next unit in spawn order (cycling at the
    /// end). Tab key handler.
    fn cycle_selection(&mut self) {
        if self.sim.turn_units.is_empty() {
            return;
        }
        let next = match self.selected {
            None => self.sim.turn_units[0],
            Some(cur) => {
                let pos = self.sim.turn_units.iter().position(|&u| u == cur);
                let next_idx = pos.map_or(0, |i| (i + 1) % self.sim.turn_units.len());
                self.sim.turn_units[next_idx]
            }
        };
        self.selected = Some(next);
    }

    /// Advance the sim cursor to the post-`edit_turn` state so the map
    /// reflects the result of running the turn currently being edited.
    fn refresh_sim(&mut self) {
        let target = (self.edit_turn + 1).min(self.opening.horizon);
        if let Err(errs) = self.sim.seek(
            &self.opening,
            Cursor {
                turn: target,
                unit_idx: 0,
            },
        ) {
            self.error = Some(format!("{} sim error(s)", errs.len()));
        }
    }

    fn map_env(&self, x: i32, y: i32) -> proto::Environment {
        let row = self.map.rows.get(y as usize);
        let tile = row.and_then(|r| r.tiles.get(x as usize)).copied();
        tile.and_then(|t| proto::Environment::try_from(t).ok())
            .unwrap_or(proto::Environment::EnvEmpty)
    }

    /// Find the engine ID of any unit covering tile `(x, y)`. The 3x3
    /// core's centre + 8 surrounding tiles all resolve to the core's id.
    fn entity_at(&self, x: i32, y: i32) -> Option<i32> {
        for (&id, e) in &self.sim.game.entities {
            let p = e.position;
            let hit = match e {
                libre_engine::game_map::Entity::Core(_) => {
                    (x - p.x).abs() <= 1 && (y - p.y).abs() <= 1
                }
                _ => p.x == x && p.y == y,
            };
            if hit {
                return Some(id);
            }
        }
        None
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
        &["opening"]
    }
    fn pick_default_dir(&self, config: &titan_core::CambcConfig) -> PathBuf {
        config.maps_path()
    }
    fn open_path(&mut self, path: PathBuf) -> Result<(), String> {
        let bytes =
            std::fs::read(&path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        let opening: Opening =
            serde_json::from_slice(&bytes).map_err(|e| format!("invalid opening file: {e}"))?;
        let map_bytes = std::fs::read(&opening.map_path)
            .map_err(|e| format!("cannot read map {}: {e}", opening.map_path.display()))?;
        let map = proto::Map::decode(&*map_bytes).map_err(|e| format!("invalid map: {e}"))?;
        let sim = Sim::from_map(&opening.map_path)?;
        self.map_path = opening.map_path.clone();
        self.map = map;
        self.opening = opening;
        self.sim = sim;
        self.opening_path = Some(path);
        self.cached_map_shapes.clear();
        self.cached_map_zoom = 0.0;
        self.selected = None;
        self.error = None;
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
        match serde_json::to_vec_pretty(&self.opening) {
            Ok(bytes) => match std::fs::write(&path, bytes) {
                Ok(_) => {
                    let display = path.display().to_string();
                    self.opening_path = Some(path);
                    let empties = count_empty_unit_turns(&self.opening);
                    self.error = if empties > 0 {
                        Some(format!(
                            "saved {display} — warning: {empties} unit-turn(s) have no actions"
                        ))
                    } else {
                        Some(format!("saved {display}"))
                    };
                }
                Err(e) => self.error = Some(format!("save: {e}")),
            },
            Err(e) => self.error = Some(format!("save: {e}")),
        }
    }
}

/// Count `(unit, turn)` cells where the action queue is empty. Used as
/// a save-time completeness warning.
fn count_empty_unit_turns(opening: &Opening) -> usize {
    let mut n = 0;
    for team in &opening.teams {
        for plan in team.units.values() {
            for slot in &plan.actions {
                if slot.items.is_empty() {
                    n += 1;
                }
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
        let (key_esc, move_dir, key_tab, key_space) = ui.ctx().input(|i| {
            let dir = if i.key_pressed(egui::Key::H) {
                Some(6) // W
            } else if i.key_pressed(egui::Key::L) {
                Some(2) // E
            } else if i.key_pressed(egui::Key::K) {
                Some(0) // N
            } else if i.key_pressed(egui::Key::J) {
                Some(4) // S
            } else {
                None
            };
            (
                i.key_pressed(egui::Key::Escape),
                dir,
                i.key_pressed(egui::Key::Tab),
                i.key_pressed(egui::Key::Space),
            )
        });
        if key_esc {
            if self.pending.is_some() {
                self.pending = None;
            } else {
                self.selected = None;
            }
        }
        if key_tab {
            self.cycle_selection();
        }
        if key_space {
            <Self as titan_core::Playback>::step_forward(self, 1);
        }
        // HJKL queues a Move on the selected builder for the edit turn.
        if let Some(dir) = move_dir
            && let Some(uid) = self.selected
            && let Some(&(team_idx, opening_id)) = self.sim.engine_to_opening.get(&uid)
            && matches!(
                self.sim.game.entities.get(&uid),
                Some(libre_engine::game_map::Entity::BuilderBot(_))
            )
        {
            let _ = self.opening.append_action(
                team_idx as usize,
                opening_id,
                self.edit_turn,
                crate::opening::Action::Move { dir },
            );
            ensure_spawn_slots(&mut self.opening);
            self.refresh_sim();
        }

        egui::Panel::right("opening-sidebar")
            .resizable(true)
            .default_size(280.0)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| {
                self.render_sidebar(ui);
            });

        egui::Panel::bottom("opening-playback")
            .exact_size(64.0)
            .resizable(false)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| {
                titan_core::render_playback_panel(ui, self, |_ui| {});
            });

        egui::CentralPanel::default().show_inside(ui, |ui| {
            self.render_map(ui);
        });
    }
}

impl App {
    fn render_sidebar(&mut self, ui: &mut egui::Ui) {
        ui.heading("opening");
        ui.label(
            self.map_path
                .file_name()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default(),
        );
        ui.separator();

        ui.label(format!(
            "editing turn: {}  (display = after this turn)",
            self.edit_turn
        ));

        // Horizon controls.
        ui.horizontal(|ui| {
            ui.label(format!("horizon: {}", self.opening.horizon));
            if ui.small_button("-").clicked() && self.opening.horizon > 1 {
                self.opening.horizon -= 1;
                truncate_to_horizon(&mut self.opening);
                if self.edit_turn >= self.opening.horizon {
                    self.edit_turn = self.opening.horizon - 1;
                }
                self.refresh_sim();
            }
            if ui.small_button("+").clicked() {
                self.opening.horizon += 1;
                extend_to_horizon(&mut self.opening);
                self.refresh_sim();
            }
        });
        ui.separator();

        let p = &self.sim.game.players;
        titan_core::style::section_title(ui, "team A");
        ui.label(format!("Ti: {}  Ax: {}", p[0].titanium, p[0].axionite));
        titan_core::style::section_title(ui, "team B");
        ui.label(format!("Ti: {}  Ax: {}", p[1].titanium, p[1].axionite));
        ui.separator();

        titan_core::style::section_title(ui, "selection");
        let mut mutated = false;
        if let Some(id) = self.selected {
            if let Some(e) = self.sim.game.entities.get(&id) {
                let team = match e.team {
                    libre_engine::common::Team::A => "A",
                    libre_engine::common::Team::B => "B",
                };
                ui.label(format!("uid {id}  team {team}"));
                ui.label(format!("pos: ({}, {})", e.position.x, e.position.y));
                ui.label(format!("hp: {}/{}", e.hp, e.max_hp));

                if let Some(&(team_idx, opening_id)) = self.sim.engine_to_opening.get(&id) {
                    let is_core = matches!(e, libre_engine::game_map::Entity::Core(_));
                    let is_builder = matches!(e, libre_engine::game_map::Entity::BuilderBot(_));
                    let turn = self.edit_turn;
                    if turn < self.opening.horizon {
                        ui.add_space(4.0);
                        titan_core::style::section_title(ui, &format!("actions @ turn {turn}"));
                        // Existing queue: click an entry to delete it.
                        let queue: Vec<(usize, String)> = self
                            .opening
                            .actions(team_idx as usize, opening_id, turn)
                            .iter()
                            .enumerate()
                            .map(|(i, a)| (i, a.label()))
                            .collect();
                        let mut delete_idx: Option<usize> = None;
                        for (i, label) in queue {
                            if ui
                                .selectable_label(false, format!("{i}. {label}  ✕"))
                                .clicked()
                            {
                                delete_idx = Some(i);
                            }
                        }
                        if let Some(idx) = delete_idx {
                            self.opening
                                .remove_action(team_idx as usize, opening_id, turn, idx);
                            mutated = true;
                        }

                        ui.add_space(4.0);
                        if is_core {
                            titan_core::style::section_title(ui, "spawn");
                            mutated |= grid_dir_buttons(
                                ui,
                                &mut self.opening,
                                team_idx as usize,
                                opening_id,
                                turn,
                                |dir| crate::opening::Action::Spawn { dir },
                                /*cardinal_only=*/ false,
                            );
                        }
                        if is_builder {
                            titan_core::style::section_title(ui, "move");
                            mutated |= grid_dir_buttons(
                                ui,
                                &mut self.opening,
                                team_idx as usize,
                                opening_id,
                                turn,
                                |dir| crate::opening::Action::Move { dir },
                                /*cardinal_only=*/ true,
                            );

                            ui.add_space(4.0);
                            titan_core::style::section_title(ui, "build (click target)");
                            ui.horizontal_wrapped(|ui| {
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildConveyor,
                                    "Conveyor",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildArmouredConveyor,
                                    "Arm.Conv",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildSplitter,
                                    "Splitter",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildBridge,
                                    "Bridge",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildHarvester,
                                    "Harvester",
                                );
                                pending_button(ui, &mut self.pending, Pending::BuildRoad, "Road");
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildBarrier,
                                    "Barrier",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildGunner,
                                    "Gunner",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildSentinel,
                                    "Sentinel",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildBreach,
                                    "Breach",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildLauncher,
                                    "Launcher",
                                );
                                pending_button(
                                    ui,
                                    &mut self.pending,
                                    Pending::BuildFoundry,
                                    "Foundry",
                                );
                            });

                            ui.add_space(4.0);
                            titan_core::style::section_title(ui, "other");
                            ui.horizontal_wrapped(|ui| {
                                pending_button(ui, &mut self.pending, Pending::Destroy, "Destroy");
                                pending_button(ui, &mut self.pending, Pending::Heal, "Heal");
                                pending_button(ui, &mut self.pending, Pending::Marker, "Marker");
                                if ui.button("Attack (own tile)").clicked() {
                                    let pos = e.position;
                                    let _ = self.opening.append_action(
                                        team_idx as usize,
                                        opening_id,
                                        turn,
                                        crate::opening::Action::Attack { x: pos.x, y: pos.y },
                                    );
                                    mutated = true;
                                }
                            });
                        }

                        // Turret rotation.
                        let is_turret = matches!(
                            e,
                            libre_engine::game_map::Entity::Gunner(_)
                                | libre_engine::game_map::Entity::Sentinel(_)
                                | libre_engine::game_map::Entity::Breach(_)
                        );
                        if is_turret {
                            ui.add_space(4.0);
                            titan_core::style::section_title(ui, "rotate");
                            mutated |= grid_dir_buttons(
                                ui,
                                &mut self.opening,
                                team_idx as usize,
                                opening_id,
                                turn,
                                |dir| crate::opening::Action::Rotate { dir },
                                /*cardinal_only=*/ false,
                            );
                        }

                        if let Some(pending) = self.pending {
                            ui.add_space(4.0);
                            ui.colored_label(
                                titan_core::style::COLOR_INFO,
                                format!("pending: {pending:?} — click target tile"),
                            );
                            if ui.small_button("cancel").clicked() {
                                self.pending = None;
                            }
                        }
                    }
                } else {
                    ui.label("(not tracked by opening)");
                }
            } else {
                ui.label(format!("uid {id} (not present)"));
            }
        } else {
            ui.label("(click a unit on the map)");
        }
        if mutated {
            ensure_spawn_slots(&mut self.opening);
            self.refresh_sim();
        }
        ui.separator();

        titan_core::style::section_title(ui, "spawn order");
        for &uid in &self.sim.turn_units {
            let label = format!("uid {uid}");
            let selected = self.selected == Some(uid);
            if ui.selectable_label(selected, label).clicked() {
                self.selected = Some(uid);
            }
        }
        ui.separator();

        ui.add_space(8.0);
        if ui.button("Export Python…").clicked() {
            let py_path = self
                .opening_path
                .clone()
                .unwrap_or_else(|| self.map_path.with_extension("opening"))
                .with_extension("py");
            match crate::export::write_python(&self.opening, &py_path) {
                Ok(()) => {
                    self.error = Some(format!("exported {}", py_path.display()));
                }
                Err(e) => self.error = Some(format!("export: {e}")),
            }
        }

        ui.add_space(4.0);
        ui.checkbox(&mut self.show_unit_ids, "Show IDs on map");

        ui.add_space(4.0);
        titan_core::style::section_title(ui, "controls");
        ui.small("Space / →    step turn");
        ui.small("←            step turn back");
        ui.small("Tab          cycle selection");
        ui.small("h/j/k/l      Move builder W/S/N/E");
        ui.small("LMB drag     pan");
        ui.small("LMB tile     select / target");
        ui.small("RMB / Esc    cancel pending / deselect");
        ui.small("wheel        zoom");

        if let Some(err) = &self.error {
            ui.add_space(8.0);
            ui.colored_label(titan_core::style::COLOR_INFO, err);
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

        // RMB cancels pending mode (or clears selection if none).
        if response.clicked_by(egui::PointerButton::Secondary) {
            if self.pending.is_some() {
                self.pending = None;
            } else {
                self.selected = None;
            }
        }

        // LMB tile click → resolve pending action target, else select.
        if response.clicked_by(egui::PointerButton::Primary)
            && let Some(pos) = response.interact_pointer_pos()
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            if let Some(pending) = self.pending.take() {
                self.dispatch_pending(pending, gx, gy);
            } else {
                self.selected = self.entity_at(gx, gy);
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

        // Selection highlight + action range ring.
        if let Some(id) = self.selected
            && let Some(e) = self.sim.game.entities.get(&id)
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

            // Show the unit's action radius while a pending tool is
            // armed — the user can target any tile inside.
            if self.pending.is_some() {
                let r_sq = action_radius_sq(e);
                let centre = titan_core::tile::tile_center(p.x, p.y, ts, origin, self.zoom);
                let r_px = (r_sq as f32).sqrt() * ts * self.zoom + ts * self.zoom * 0.5;
                painter.circle_stroke(
                    centre,
                    r_px,
                    egui::Stroke::new(
                        1.5,
                        egui::Color32::from_rgba_premultiplied(0xff, 0xc0, 0x40, 0xa0),
                    ),
                );
            }
        }

        // Hover preview tile while pending.
        if self.pending.is_some()
            && response.hovered()
            && let Some(pos) = ui.ctx().input(|i| i.pointer.hover_pos())
        {
            let gx = ((pos.x - origin.x) / (ts * self.zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * self.zoom)).floor() as i32;
            if gx >= 0 && gx < w && gy >= 0 && gy < h {
                ui.ctx().set_cursor_icon(egui::CursorIcon::Crosshair);
                painter.rect_stroke(
                    tile_rect(gx, gy, ts, origin, self.zoom),
                    0.0,
                    egui::Stroke::new(2.0, egui::Color32::WHITE),
                    egui::StrokeKind::Outside,
                );
            }
        }
    }
}

const fn action_radius_sq(e: &libre_engine::game_map::Entity) -> i32 {
    use libre_engine::common::game_constants as gc;
    match e {
        libre_engine::game_map::Entity::BuilderBot(_) => gc::ACTION_RADIUS_SQ,
        libre_engine::game_map::Entity::Core(_) => gc::CORE_SPAWNING_RADIUS_SQ,
        _ => 0,
    }
}

impl App {
    /// Resolve a pending action with the clicked tile and append it to
    /// the selected unit's action queue at the current turn. Direction
    /// (where applicable) is the 8-way vector from unit to target.
    fn dispatch_pending(&mut self, pending: Pending, x: i32, y: i32) {
        let Some(uid) = self.selected else {
            return;
        };
        let Some(&(team_idx, opening_id)) = self.sim.engine_to_opening.get(&uid) else {
            return;
        };
        let from = match self.sim.game.entities.get(&uid) {
            Some(e) => (e.position.x, e.position.y),
            None => return,
        };
        let dir = vec_to_dir((x - from.0, y - from.1));
        let action = match pending {
            Pending::BuildConveyor => crate::opening::Action::BuildConveyor { x, y, dir },
            Pending::BuildArmouredConveyor => {
                crate::opening::Action::BuildArmouredConveyor { x, y, dir }
            }
            Pending::BuildSplitter => crate::opening::Action::BuildSplitter { x, y, dir },
            Pending::BuildBridge => crate::opening::Action::BuildBridge {
                x: from.0,
                y: from.1,
                tx: x,
                ty: y,
            },
            Pending::BuildHarvester => crate::opening::Action::BuildHarvester { x, y },
            Pending::BuildRoad => crate::opening::Action::BuildRoad { x, y },
            Pending::BuildBarrier => crate::opening::Action::BuildBarrier { x, y },
            Pending::BuildGunner => crate::opening::Action::BuildGunner { x, y, dir },
            Pending::BuildSentinel => crate::opening::Action::BuildSentinel { x, y, dir },
            Pending::BuildBreach => crate::opening::Action::BuildBreach { x, y, dir },
            Pending::BuildLauncher => crate::opening::Action::BuildLauncher { x, y },
            Pending::BuildFoundry => crate::opening::Action::BuildFoundry { x, y },
            Pending::Destroy => crate::opening::Action::Destroy { x, y },
            Pending::Heal => crate::opening::Action::Heal { x, y },
            Pending::Marker => crate::opening::Action::PlaceMarker { x, y, value: 0 },
        };
        let turn = self.edit_turn;
        let _ = self
            .opening
            .append_action(team_idx as usize, opening_id, turn, action);
        ensure_spawn_slots(&mut self.opening);
        self.refresh_sim();
    }
}

/// 8-way direction encoding the displacement vector.
fn vec_to_dir((dx, dy): (i32, i32)) -> i32 {
    match (dx.signum(), dy.signum()) {
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

fn pending_button(ui: &mut egui::Ui, pending: &mut Option<Pending>, target: Pending, label: &str) {
    let active =
        matches!(pending, Some(p) if std::mem::discriminant(p) == std::mem::discriminant(&target));
    let resp = ui.selectable_label(active, label);
    if resp.clicked() {
        *pending = if active { None } else { Some(target) };
    }
}

/// 3×3 grid of direction buttons. Cardinal-only renders only N/E/S/W
/// (corners empty). Returns `true` if a button fired and the action
/// was appended.
fn grid_dir_buttons(
    ui: &mut egui::Ui,
    opening: &mut Opening,
    team_idx: usize,
    opening_id: u32,
    turn: usize,
    make: impl Fn(i32) -> crate::opening::Action,
    cardinal_only: bool,
) -> bool {
    // Layout: 3×3, dir indices laid out as the 8 compass points.
    //   NW N NE        7 0 1
    //    W . E    →    6 . 2
    //   SW S SE        5 4 3
    const DIRS: [Option<i32>; 9] = [
        Some(7),
        Some(0),
        Some(1),
        Some(6),
        None,
        Some(2),
        Some(5),
        Some(4),
        Some(3),
    ];
    const LABELS: [&str; 9] = ["↖", "↑", "↗", "←", "·", "→", "↙", "↓", "↘"];
    let mut fired = false;
    egui::Grid::new(("dir-grid", team_idx, opening_id, turn))
        .num_columns(3)
        .spacing([4.0, 4.0])
        .show(ui, |ui| {
            for i in 0..9 {
                let dir = DIRS[i];
                let cardinal = matches!(dir, Some(0 | 2 | 4 | 6));
                let enabled = dir.is_some() && (!cardinal_only || cardinal);
                let resp = ui.add_enabled(enabled, egui::Button::new(LABELS[i]));
                if enabled
                    && resp.clicked()
                    && let Some(d) = dir
                {
                    let _ = opening.append_action(team_idx, opening_id, turn, make(d));
                    fired = true;
                }
                if (i + 1) % 3 == 0 {
                    ui.end_row();
                }
            }
        });
    fired
}

/// Walk every team's core action queues and ensure there's a UnitPlan
/// allocated for each `Spawn` action — one builder UnitPlan per Spawn,
/// in the order Spawns appear across the timeline. Idempotent.
fn ensure_spawn_slots(opening: &mut Opening) {
    let horizon = opening.horizon;
    for team_idx in 0..2 {
        // Count Spawns in chronological order from the core's queue.
        let mut spawn_turns: Vec<usize> = Vec::new();
        if let Some(core) = opening.teams[team_idx]
            .units
            .get(&crate::opening::CORE_OPENING_ID)
        {
            for (rel, turn_acts) in core.actions.iter().enumerate() {
                let turn = core.spawn_turn + rel;
                for act in &turn_acts.items {
                    if matches!(act, crate::opening::Action::Spawn { .. }) {
                        spawn_turns.push(turn + 1);
                    }
                }
            }
        }
        // Builder UnitPlans live at opening_ids 1..=spawn_turns.len().
        for (i, &spawn_turn) in spawn_turns.iter().enumerate() {
            let id = (i + 1) as u32;
            let n = horizon.saturating_sub(spawn_turn);
            opening.teams[team_idx]
                .units
                .entry(id)
                .or_insert_with(|| crate::opening::UnitPlan {
                    spawn_turn,
                    actions: vec![crate::opening::TurnActions::default(); n],
                });
        }
        // Trim any orphaned UnitPlans beyond the spawn count (deleted spawns).
        let keep_up_to = spawn_turns.len() as u32;
        opening.teams[team_idx]
            .units
            .retain(|&k, _| k == 0 || k <= keep_up_to);
    }
}

/// Truncate every unit's action vector to fit within the new horizon.
fn truncate_to_horizon(opening: &mut Opening) {
    for team in &mut opening.teams {
        for plan in team.units.values_mut() {
            let max = opening.horizon.saturating_sub(plan.spawn_turn);
            plan.actions.truncate(max);
        }
    }
}

/// Append empty action queues so every unit covers the new horizon.
fn extend_to_horizon(opening: &mut Opening) {
    for team in &mut opening.teams {
        for plan in team.units.values_mut() {
            let needed = opening.horizon.saturating_sub(plan.spawn_turn);
            while plan.actions.len() < needed {
                plan.actions.push(crate::opening::TurnActions::default());
            }
        }
    }
}
