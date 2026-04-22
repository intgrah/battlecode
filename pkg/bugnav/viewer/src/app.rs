use std::path::PathBuf;

use cambc_common::{SpriteAtlas, SpriteConfig};
use eframe::egui;

use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, StepStatus, registry, shortest_path};

pub struct App {
    pub grid: Grid,
    pub atlas: SpriteAtlas,
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
    pub steps_per_frame: u32,
    pub show_vision: bool,

    pub pan: egui::Vec2,
    pub zoom: f32,
    pub cached_map_shapes: Vec<egui::Shape>,
    pub cached_map_origin: egui::Vec2,
    pub cached_map_zoom: f32,
}

impl App {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        grid: Grid,
        assets_dir: &std::path::Path,
        map_paths: Vec<PathBuf>,
        map_idx: usize,
    ) -> Self {
        cambc_common::style::apply_dark_text(&cc.egui_ctx);
        let atlas = SpriteAtlas::load(
            cc,
            assets_dir,
            SpriteConfig {
                strip_sprites: &[],
                aspect_sprites: &[],
                rotatable_sprites: &[],
            },
        );
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
            steps_per_frame: 1,
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
    }

    pub fn step_once(&mut self) {
        if let Some(f) = self.finder.as_mut() {
            self.last_status = f.step();
            if self.last_status != StepStatus::Running {
                self.playing = false;
            }
        }
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        if self.playing {
            for _ in 0..self.steps_per_frame {
                if self.last_status != StepStatus::Running {
                    self.playing = false;
                    break;
                }
                self.step_once();
            }
            ui.ctx().request_repaint();
        }

        egui::Panel::right("sidebar")
            .resizable(false)
            .default_size(260.0)
            .show_inside(ui, |ui| crate::ui::render_sidebar(ui, self));
        egui::CentralPanel::default().show_inside(ui, |ui| crate::ui::render_map_panel(ui, self));
    }
}
