use std::path::PathBuf;
use std::sync::Arc;

use eframe::egui;
use titan_core::SpriteSet;

use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, StepStatus, registry, shortest_path};

pub struct App {
    pub grid: Grid,
    pub atlas: Arc<SpriteSet>,
    pub map_names: Vec<String>,
    pub map_paths: Vec<PathBuf>,
    pub map_idx: usize,
    pub algo_idx: usize,

    pub start: Option<(i32, i32)>,
    pub goal: Option<(i32, i32)>,
    pub finder: Option<Box<dyn Pathfinder>>,
    pub last_status: StepStatus,
    pub optimal_path: Option<Vec<(i32, i32)>>,

    pub playing: bool,
    /// Discrete speed level 0..=8 → 2^level steps per frame when playing.
    pub speed: i32,
    /// Number of `step` calls since the last `reset_finder`.
    pub step_count: usize,
    pub show_vision: bool,

    pub pan: egui::Vec2,
    pub zoom: f32,
    pub cached_map_shapes: Vec<egui::Shape>,
    pub cached_map_origin: egui::Vec2,
    pub cached_map_zoom: f32,
}

impl App {
    #[must_use]
    pub fn new(atlas: Arc<SpriteSet>, grid: Grid, map_paths: Vec<PathBuf>, map_idx: usize) -> Self {
        let map_names = map_paths
            .iter()
            .map(|p| {
                p.file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("?")
                    .to_string()
            })
            .collect();
        Self {
            grid,
            atlas,
            map_names,
            map_paths,
            map_idx,
            algo_idx: 0,
            start: None,
            goal: None,
            finder: None,
            last_status: StepStatus::Running,
            optimal_path: None,
            playing: false,
            speed: 0,
            step_count: 0,
            show_vision: true,
            pan: egui::Vec2::new(10.0, 10.0),
            zoom: 1.0,
            cached_map_shapes: Vec::new(),
            cached_map_origin: egui::Vec2::ZERO,
            cached_map_zoom: 0.0,
        }
    }

    pub fn load_selected_map(&mut self) {
        let Some(path) = self.map_paths.get(self.map_idx) else {
            return;
        };
        match Grid::load(path) {
            Ok(g) => {
                self.grid = g;
                self.start = None;
                self.goal = None;
                self.finder = None;
                self.optimal_path = None;
                self.last_status = StepStatus::Running;
                self.step_count = 0;
                self.cached_map_zoom = 0.0; // invalidate cache
            }
            Err(e) => eprintln!("load map: {e}"),
        }
    }

    pub fn reset_finder(&mut self) {
        if let (Some(s), Some(g)) = (self.start, self.goal) {
            let build = registry()[self.algo_idx].build;
            self.finder = Some(build(&self.grid, s, g));
            self.last_status = StepStatus::Running;
            self.optimal_path = shortest_path(&self.grid, s, g);
        } else {
            self.finder = None;
            self.optimal_path = None;
        }
        self.step_count = 0;
    }

    pub fn step_once(&mut self) {
        if let Some(f) = self.finder.as_mut() {
            self.last_status = f.step();
            self.step_count += 1;
            if self.last_status != StepStatus::Running {
                self.playing = false;
            }
        }
    }

    pub fn load_path(&mut self, path: PathBuf) -> Result<(), String> {
        let grid = Grid::load(&path)?;
        self.grid = grid;
        if let Some(idx) = self.map_paths.iter().position(|p| p == &path) {
            self.map_idx = idx;
        }
        self.start = None;
        self.goal = None;
        self.finder = None;
        self.optimal_path = None;
        self.last_status = StepStatus::Running;
        self.step_count = 0;
        self.cached_map_zoom = 0.0;
        Ok(())
    }
}

impl titan_core::ModeApp for App {
    fn name(&self) -> &'static str {
        "bugnav"
    }
    fn current_path(&self) -> Option<&std::path::Path> {
        self.map_paths.get(self.map_idx).map(PathBuf::as_path)
    }
    fn pick_extensions(&self) -> &'static [&'static str] {
        &["map26"]
    }
    fn pick_default_dir(&self, config: &titan_core::CambcConfig) -> PathBuf {
        config.maps_path()
    }
    fn open_path(&mut self, path: PathBuf) -> Result<(), String> {
        self.load_path(path)
    }
}

impl titan_core::Playback for App {
    fn position(&self) -> usize {
        self.step_count
    }
    fn total(&self) -> usize {
        // Optimal path length is the natural denominator: shows whether
        // the algorithm is on track. Falls back to step_count so the bar
        // is always meaningful if optimal isn't known yet.
        self.optimal_path
            .as_ref()
            .map(|p| p.len().saturating_sub(1).max(1))
            .unwrap_or_else(|| self.step_count.max(1))
    }
    fn playing(&self) -> bool {
        self.playing
    }
    fn toggle_play(&mut self) {
        if self.finder.is_some() && self.last_status == StepStatus::Running {
            self.playing = !self.playing;
        }
    }
    fn step_forward(&mut self, n: usize) {
        for _ in 0..n {
            if self.last_status != StepStatus::Running {
                break;
            }
            self.step_once();
        }
    }
    fn step_back(&mut self, _n: usize) {
        // Pathfinding is unidirectional.
    }
    fn seek(&mut self, _position: usize) {
        // Pathfinding is unidirectional.
    }
    fn speed(&self) -> i32 {
        self.speed
    }
    fn set_speed(&mut self, speed: i32) {
        self.speed = speed;
    }
    fn supports_step_back(&self) -> bool {
        false
    }
    fn supports_seek(&self) -> bool {
        false
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        // Space steps one algorithm tick — alias for the playback strip's
        // step-forward so the keybinding matches replay/opening.
        if ui.ctx().input(|i| i.key_pressed(egui::Key::Space)) {
            self.step_once();
        }

        if self.playing {
            let steps = titan_core::playback::speed_multiplier(self.speed) as usize;
            for _ in 0..steps {
                if self.last_status != StepStatus::Running {
                    self.playing = false;
                    break;
                }
                self.step_once();
            }
            ui.ctx().request_repaint();
        }

        egui::Panel::right("sidebar")
            .resizable(true)
            .default_size(260.0)
            .frame(titan_core::style::panel_frame(ui.style()))
            .show_inside(ui, |ui| crate::ui::render_sidebar(ui, self));
        crate::ui::render_scrubber(ui, self);
        egui::CentralPanel::default().show_inside(ui, |ui| crate::ui::render_map_panel(ui, self));
    }
}
