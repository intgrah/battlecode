use std::fs;
use std::path::PathBuf;
use std::time::{Duration, Instant, SystemTime};

use eframe::egui;
use egui::{FontData, FontDefinitions, FontFamily};
use prost::Message;

use crate::map;
use crate::proto;
use crate::sprites::SpriteAtlas;
use crate::state::{Entity, EntityKind, GameState};
use crate::ui;

const FONT: &[u8] = include_bytes!("../assets/font.ttf");

fn configure_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    fonts
        .font_data
        .insert("mono".into(), FontData::from_static(FONT).into());
    fonts
        .families
        .entry(FontFamily::Proportional)
        .or_default()
        .insert(0, "mono".into());
    fonts
        .families
        .entry(FontFamily::Monospace)
        .or_default()
        .insert(0, "mono".into());
    ctx.set_fonts(fonts);
}

#[allow(clippy::struct_excessive_bools)]
pub struct App {
    pub game: GameState,
    pub atlas: SpriteAtlas,
    pub turn: usize,
    pub playing: bool,
    pub speed: i32,
    pub cursor: (i32, i32),
    pub selected_entity: Option<i32>,
    pub follow_entity: bool,
    pub show_indicators: bool,
    pub show_flow: bool,
    pub show_ranges: bool,
    pub vis_overlays: std::collections::HashSet<String>,
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
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        replay: &proto::Replay,
        assets_dir: &std::path::Path,
        replay_path: PathBuf,
    ) -> Self {
        configure_fonts(&cc.egui_ctx);
        let mut style = (*cc.egui_ctx.global_style()).clone();
        style.visuals.override_text_color = Some(egui::Color32::from_rgb(0xe0, 0xe0, 0xe0));
        style.visuals.widgets.noninteractive.fg_stroke.color =
            egui::Color32::from_rgb(0xe0, 0xe0, 0xe0);
        style.visuals.widgets.inactive.fg_stroke.color = egui::Color32::from_rgb(0xd0, 0xd0, 0xd0);
        cc.egui_ctx.set_global_style(style);
        cc.egui_ctx.tessellation_options_mut(|opts| {
            opts.feathering = true;
            opts.feathering_size_in_pixels = 1.5;
        });
        let atlas = SpriteAtlas::load(cc, assets_dir);
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
            selected_entity: None,
            follow_entity: false,
            show_indicators: false,
            show_flow: false,
            show_ranges: true,
            vis_overlays: std::collections::HashSet::new(),
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

    pub const fn tick_ms(&self) -> u64 {
        500 / (1u64 << self.speed as u64)
    }

    pub const fn speed_label(&self) -> u32 {
        1 << self.speed as u32
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

    pub fn load_replay(&mut self, path: PathBuf) {
        let Ok(data) = fs::read(&path) else {
            eprintln!("Cannot read {}", path.display());
            return;
        };
        let Ok(replay) = proto::Replay::decode(&*data) else {
            eprintln!("Invalid replay: {}", path.display());
            return;
        };
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
                self.toggle_playing();
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

        ui::render_left_sidebar(ui, self);
        ui::render_right_sidebar(ui, self);
        ui::render_scrubber(ui, self);
        map::render_map_panel(ui, self);
    }
}
