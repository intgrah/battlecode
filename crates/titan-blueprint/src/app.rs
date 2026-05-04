use std::path::{Path, PathBuf};
use std::sync::Arc;

use eframe::egui;

use crate::blueprint::Entity;
use crate::map::MapData;
use crate::state::Editor;
use titan_core::SpriteSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    View,
    Place(Entity),
    PhaseView,
}

pub struct App {
    pub map: MapData,
    pub map_path: Option<PathBuf>,
    pub editor: Editor,
    pub atlas: Arc<SpriteSet>,
    pub pan: egui::Vec2,
    pub zoom: f32,
    pub hover_tile: Option<(i32, i32)>,
    pub cached_map_shapes: Vec<egui::Shape>,
    pub cached_map_origin: egui::Vec2,
    pub cached_map_zoom: f32,
    pub drag_last_tile: Option<(i32, i32)>,
    pub show_connected_textures: bool,
    pub mode: Mode,
    pub focused: Option<(i32, i32)>,
    pub show_flow: bool,
    should_quit: bool,
}

impl App {
    pub fn new(atlas: Arc<SpriteSet>, map: MapData, map_path: Option<PathBuf>) -> Self {
        let sym = crate::symmetry::detect(&map).unwrap_or(crate::symmetry::Symmetry::Rot);
        let mut editor = Editor::new(&map, sym);

        if let Some(entries) = crate::bp_io::load_bp(&map.name) {
            let n = entries.len();
            editor.state.load(entries);
            editor.status = format!("loaded {n} entries");
        }

        Self {
            map,
            map_path,
            editor,
            atlas,
            pan: egui::Vec2::new(10.0, 10.0),
            zoom: 1.0,
            hover_tile: None,
            cached_map_shapes: Vec::new(),
            cached_map_origin: egui::Vec2::ZERO,
            cached_map_zoom: 0.0,
            drag_last_tile: None,
            show_connected_textures: true,
            mode: Mode::View,
            focused: None,
            show_flow: true,
            should_quit: false,
        }
    }

    pub fn load_map(&mut self, path: PathBuf) -> Result<(), String> {
        let map = crate::map::load(&path)?;
        let sym = crate::symmetry::detect(&map).unwrap_or(crate::symmetry::Symmetry::Rot);
        let mut editor = Editor::new(&map, sym);
        if let Some(entries) = crate::bp_io::load_bp(&map.name) {
            let n = entries.len();
            editor.state.load(entries);
            editor.status = format!("loaded {n} entries");
        }
        self.map = map;
        self.editor = editor;
        self.map_path = Some(path);
        self.cached_map_shapes.clear();
        self.cached_map_zoom = 0.0;
        self.focused = None;
        self.hover_tile = None;
        Ok(())
    }
}

impl titan_core::ModeApp for App {
    fn name(&self) -> &'static str {
        "blueprint"
    }
    fn current_path(&self) -> Option<&Path> {
        self.map_path.as_deref()
    }
    fn pick_extensions(&self) -> &'static [&'static str] {
        &["map26", "bp"]
    }
    fn pick_default_dir(&self, config: &titan_core::CambcConfig) -> PathBuf {
        config.maps_path()
    }
    fn open_path(&mut self, path: PathBuf) -> Result<(), String> {
        if path.extension().and_then(|s| s.to_str()) == Some("bp") {
            let inputs = crate::parse_args(vec![
                std::ffi::OsString::new(),
                path.into_os_string(),
            ])?;
            self.load_map(inputs.map_path)
        } else {
            self.load_map(path)
        }
    }
    fn can_save(&self) -> bool {
        true
    }
    fn save_file(&mut self) {
        self.editor.save();
    }
    fn can_undo(&self) -> bool {
        self.editor.state.can_undo()
    }
    fn undo(&mut self) {
        self.editor.state.undo();
    }
    fn can_redo(&self) -> bool {
        self.editor.state.can_redo()
    }
    fn redo(&mut self) {
        self.editor.state.redo();
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
            .resizable(true)
            .default_size(260.0)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| {
                crate::ui::render_sidebar(ui, self);
            });

        egui::CentralPanel::default().show_inside(ui, |ui| {
            crate::map_view::render(ui, self);
        });
    }
}
