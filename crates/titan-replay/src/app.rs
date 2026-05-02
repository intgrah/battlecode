use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};

use eframe::egui;
use prost::Message;

use crate::map;
use crate::proto;
use crate::state::{Entity, EntityKind, GameState};
use crate::ui;
use titan_core::SpriteSet;

#[allow(clippy::struct_excessive_bools)]
pub struct App {
    pub game: GameState,
    pub atlas: Arc<SpriteSet>,
    pub turn: usize,
    pub playing: bool,
    pub speed: i32,
    pub cursor: (i32, i32),
    pub hover_tile: Option<(i32, i32)>,
    pub selected_entity: Option<i32>,
    pub follow_entity: bool,
    pub show_indicators: bool,
    pub show_flow: bool,
    pub show_ranges: bool,
    pub show_connected_textures: bool,
    pub use_plain_roads: bool,
    pub highlight_builders: bool,
    /// Sticky overlays: names of vis fields to render on the map.
    /// Click a row to toggle. Multiple may be active simultaneously.
    pub selected_vis_overlays: std::collections::HashSet<String>,
    /// Transient overlay: set per-frame when the user hovers a row.
    /// Renders in addition to `selected_vis_overlays` so hovering
    /// previews without committing.
    pub hovered_vis_overlay: Option<String>,
    pub pan: egui::Vec2,
    pub zoom: f32,
    pub interp_t: f32,
    pub cached_map_shapes: Vec<egui::Shape>,
    pub cached_map_origin: egui::Vec2,
    pub cached_map_zoom: f32,
    replay_path: PathBuf,
    last_modified: SystemTime,
    last_step: Instant,
}

impl App {
    #[must_use]
    pub fn new(atlas: Arc<SpriteSet>, replay: &proto::Replay, replay_path: PathBuf) -> Self {
        let game = GameState::from_replay(replay);
        let last_modified = fs::metadata(&replay_path)
            .and_then(|m| m.modified())
            .unwrap_or(SystemTime::UNIX_EPOCH);
        Self {
            game,
            atlas,
            turn: 0,
            playing: false,
            speed: 0,
            cursor: (0, 0),
            hover_tile: None,
            selected_entity: None,
            follow_entity: false,
            show_indicators: false,
            show_flow: false,
            show_ranges: true,
            show_connected_textures: true,
            use_plain_roads: true,
            highlight_builders: false,
            selected_vis_overlays: std::collections::HashSet::new(),
            hovered_vis_overlay: None,
            pan: egui::Vec2::ZERO,
            zoom: 1.0,
            interp_t: 0.0,
            cached_map_shapes: Vec::new(),
            cached_map_origin: egui::Vec2::new(f32::NAN, f32::NAN),
            cached_map_zoom: f32::NAN,
            replay_path,
            last_modified,
            last_step: Instant::now(),
        }
    }

    #[must_use]
    pub const fn tick_ms(&self) -> u64 {
        500 / (1u64 << self.speed as u64)
    }

    pub fn toggle_playing(&mut self) {
        self.playing = !self.playing;
        self.last_step = Instant::now();
    }

    pub fn step_forward(&mut self, n: usize) {
        self.turn = (self.turn + n).min(self.game.turn_count());
        if self.turn >= self.game.turn_count() {
            self.playing = false;
        }
    }

    pub const fn step_backward(&mut self, n: usize) {
        self.turn = self.turn.saturating_sub(n);
    }

    pub fn select_at_cursor(&mut self) {
        let state = &self.game.turns[self.turn];
        let at_cursor: Vec<&Entity> = state
            .entities
            .values()
            .filter(|e| e.pos == (self.cursor.0, self.cursor.1))
            .collect();

        let builder = at_cursor
            .iter()
            .find(|e| matches!(e.kind, EntityKind::BuilderBot { .. }));

        if let Some(b) = builder {
            self.selected_entity = Some(b.id);
            self.follow_entity = true;
        } else {
            self.selected_entity = at_cursor.first().map(|e| e.id);
            self.follow_entity = false;
        }
    }

    pub fn load_replay(&mut self, path: PathBuf) -> Result<(), String> {
        let data = fs::read(&path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        let replay = proto::Replay::decode(&*data).map_err(|e| format!("invalid replay: {e}"))?;
        self.game = GameState::from_replay(&replay);
        self.turn = 0;
        self.playing = false;
        self.selected_entity = None;
        self.follow_entity = false;
        self.replay_path = path;
        self.last_modified = fs::metadata(&self.replay_path)
            .and_then(|m| m.modified())
            .unwrap_or(SystemTime::UNIX_EPOCH);
        self.cached_map_shapes.clear();
        self.cached_map_zoom = f32::NAN;
        Ok(())
    }

    fn check_hot_reload(&mut self) {
        if let Ok(meta) = fs::metadata(&self.replay_path)
            && let Ok(modified) = meta.modified()
            && modified != self.last_modified
            && let Ok(new_data) = fs::read(&self.replay_path)
            && let Ok(new_replay) = proto::Replay::decode(&*new_data)
        {
            self.game = GameState::from_replay(&new_replay);
            self.turn = 0;
            self.playing = false;
            self.selected_entity = None;
            self.follow_entity = false;
            self.last_modified = modified;
            self.cached_map_shapes.clear();
            self.cached_map_zoom = f32::NAN;
        }
    }

    fn handle_keys(&mut self, ctx: &egui::Context) {
        ctx.input(|i| {
            use egui::Key;
            let shift = i.modifiers.shift;

            if i.key_pressed(Key::Escape) && self.selected_entity.is_some() {
                self.selected_entity = None;
                self.follow_entity = false;
            }
            if i.key_pressed(Key::Space) {
                self.step_forward(1);
            }
            if i.key_pressed(Key::ArrowRight) {
                if shift {
                    self.step_forward(10);
                } else {
                    self.step_forward(1);
                }
            }
            if i.key_pressed(Key::ArrowLeft) {
                if shift {
                    self.step_backward(10);
                } else {
                    self.step_backward(1);
                }
            }
            if i.key_pressed(Key::Home) {
                self.turn = 0;
            }
            if i.key_pressed(Key::End) {
                self.turn = self.game.turn_count();
            }
            if i.key_pressed(Key::H) {
                self.cursor.0 = (self.cursor.0 - 1).max(0);
            }
            if i.key_pressed(Key::J) {
                self.cursor.1 = (self.cursor.1 + 1).min(self.game.height - 1);
            }
            if i.key_pressed(Key::K) {
                self.cursor.1 = (self.cursor.1 - 1).max(0);
            }
            if i.key_pressed(Key::L) {
                self.cursor.0 = (self.cursor.0 + 1).min(self.game.width - 1);
            }
            if i.key_pressed(Key::Enter) {
                self.select_at_cursor();
            }
            if i.key_pressed(Key::I) {
                self.show_indicators = !self.show_indicators;
            }
            if i.key_pressed(Key::F) {
                self.show_flow = !self.show_flow;
            }

            if i.key_pressed(Key::Equals) || i.key_pressed(Key::Plus) {
                self.speed = (self.speed + 1).min(8);
            }
            if i.key_pressed(Key::Minus) && !shift {
                self.speed = (self.speed - 1).max(0);
            }

            if i.key_pressed(Key::G) {
                if shift {
                    self.turn = self.game.turn_count();
                } else {
                    self.turn = 0;
                }
            }

            for c in '1'..='9' {
                if i.key_pressed(Key::from_name(&c.to_string()).unwrap()) {
                    let frac = f64::from(c as u8 - b'0') / 10.0;
                    self.turn = (frac * self.game.turn_count() as f64) as usize;
                }
            }
        });
    }
}

impl titan_core::ModeApp for App {
    fn name(&self) -> &'static str {
        "replay"
    }
    fn current_path(&self) -> Option<&std::path::Path> {
        Some(&self.replay_path)
    }
    fn pick_extensions(&self) -> &'static [&'static str] {
        &["replay26"]
    }
    fn pick_default_dir(&self, config: &titan_core::CambcConfig) -> PathBuf {
        config.project_root.clone()
    }
    fn open_path(&mut self, path: PathBuf) -> Result<(), String> {
        self.load_replay(path)
    }
}

impl titan_core::Playback for App {
    fn position(&self) -> usize {
        self.turn
    }
    fn total(&self) -> usize {
        self.game.turn_count()
    }
    fn playing(&self) -> bool {
        self.playing
    }
    fn toggle_play(&mut self) {
        self.toggle_playing();
    }
    fn step_forward(&mut self, n: usize) {
        Self::step_forward(self, n);
    }
    fn step_back(&mut self, n: usize) {
        self.step_backward(n);
    }
    fn seek(&mut self, position: usize) {
        self.turn = position.min(self.game.turn_count());
    }
    fn speed(&self) -> i32 {
        self.speed
    }
    fn set_speed(&mut self, speed: i32) {
        self.speed = speed;
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        self.check_hot_reload();

        if self.playing {
            let tick = Duration::from_millis(self.tick_ms());
            let elapsed = self.last_step.elapsed();
            if elapsed >= tick {
                let steps = (elapsed.as_nanos() / tick.as_nanos().max(1)).min(50) as usize;
                self.step_forward(steps.max(1));
                self.last_step = Instant::now();
                self.interp_t = 0.0;
            } else {
                self.interp_t = (elapsed.as_secs_f32() / tick.as_secs_f32()).clamp(0.0, 1.0);
            }
            ctx.request_repaint();
        } else {
            self.interp_t = 0.0;
        }

        if self.follow_entity
            && let Some(id) = self.selected_entity
            && let Some(e) = self.game.turns[self.turn].entities.get(&id)
        {
            self.cursor = e.pos;
        }

        self.handle_keys(&ctx);

        // Transient hover highlight: cleared once per frame here so any
        // panel rendered below can set it without being clobbered by a
        // later panel's per-frame reset.
        self.hover_tile = None;

        ui::render_left_sidebar(ui, self);
        // Order matters for additive sizing: each `Panel::right` carves
        // its space off the remaining area. Render `log` first so it
        // sits at the far right; `state_dump` then carves off space to
        // the left of the log. Both are independently resizable.
        ui::render_log_panel(ui, self);
        ui::render_state_dump_panel(ui, self);
        ui::render_top_panel(ui, self);
        ui::render_scrubber(ui, self);
        map::render_map_panel(ui, self);
    }
}
