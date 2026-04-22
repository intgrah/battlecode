use eframe::egui;

use crate::blueprint::Entity;
use crate::map::MapData;
use cambc_common::{SpriteAtlas, SpriteConfig};
use crate::state::Editor;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    View,
    Place(Entity),
    Erase,
    PhaseView,
}

pub struct App {
    pub map: MapData,
    pub editor: Editor,
    pub atlas: SpriteAtlas,
    pub pan: egui::Vec2,
    pub zoom: f32,
    pub hover_tile: Option<(i32, i32)>,
    pub cached_map_shapes: Vec<egui::Shape>,
    pub cached_map_origin: egui::Vec2,
    pub cached_map_zoom: f32,
    pub drag_last_tile: Option<(i32, i32)>,
    pub show_conveyor_junctions: bool,
    pub mode: Mode,
    pub focused: Option<(i32, i32)>,
    should_quit: bool,
}

impl App {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        map: MapData,
        assets_dir: &std::path::Path,
    ) -> Self {
        let mut style = (*cc.egui_ctx.global_style()).clone();
        style.visuals.override_text_color = Some(egui::Color32::from_rgb(0xe0, 0xe0, 0xe0));
        cc.egui_ctx.set_global_style(style);
        cc.egui_ctx.tessellation_options_mut(|opts| {
            opts.feathering = true;
            opts.feathering_size_in_pixels = 1.5;
        });

        let atlas = SpriteAtlas::load(
            cc,
            assets_dir,
            SpriteConfig {
                strip_sprites: &["bridge_gold", "bridge_silver"],
                aspect_sprites: &[],
                rotatable_sprites: &[
                    "conveyor_gold",
                    "conveyor_silver",
                    "armoured_conveyor_gold",
                    "armoured_conveyor_silver",
                ],
            },
        );
        let sym = crate::symmetry::detect(&map).unwrap_or(crate::symmetry::Symmetry::Rot);
        let mut editor = Editor::new(&map, sym);

        if let Some(entries) = crate::bp_io::load_bp(&map.name) {
            let n = entries.len();
            editor.state.load(entries);
            editor.status = format!("loaded {n} entries");
        }

        Self {
            map,
            editor,
            atlas,
            pan: egui::Vec2::new(10.0, 10.0),
            zoom: 1.0,
            hover_tile: None,
            cached_map_shapes: Vec::new(),
            cached_map_origin: egui::Vec2::ZERO,
            cached_map_zoom: 0.0,
            drag_last_tile: None,
            show_conveyor_junctions: false,
            mode: Mode::View,
            focused: None,
            should_quit: false,
        }
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        if crate::ui::handle_keys(&ctx, self) {
            self.should_quit = true;
        }
        if self.should_quit {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }

        egui::Panel::right("sidebar")
            .resizable(false)
            .default_size(260.0)
            .show_inside(ui, |ui| {
                crate::ui::render_sidebar(ui, self);
            });

        egui::CentralPanel::default().show_inside(ui, |ui| {
            crate::map_view::render(ui, self);
        });
    }
}
