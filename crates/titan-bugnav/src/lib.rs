pub mod algorithms;
pub mod app;
pub mod grid;
pub mod pathfinder;
pub mod render;
pub mod ui;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use titan_core::SpriteSet;

fn find_maps_dir() -> Option<PathBuf> {
    let candidates = [
        Path::new("maps").to_path_buf(),
        Path::new("../maps").to_path_buf(),
        Path::new("../../maps").to_path_buf(),
    ];
    candidates.iter().find(|p| p.is_dir()).cloned()
}

fn collect_maps(dir: &Path) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = std::fs::read_dir(dir)
        .ok()
        .into_iter()
        .flat_map(std::iter::Iterator::flatten)
        .map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().and_then(|s| s.to_str()) == Some("map26"))
        .collect();
    out.sort();
    out
}

pub struct Inputs {
    pub grid: grid::Grid,
    pub map_paths: Vec<PathBuf>,
    pub initial_idx: usize,
}

pub fn parse_args(args: Vec<OsString>) -> Result<Inputs, String> {
    let arg_path = args
        .into_iter()
        .nth(1)
        .map(|a| a.to_string_lossy().into_owned());

    let maps_dir = find_maps_dir()
        .ok_or_else(|| "cannot find maps/ directory from cwd or ancestors".to_string())?;
    let map_paths = collect_maps(&maps_dir);
    if map_paths.is_empty() {
        return Err(format!("no .map26 files in {}", maps_dir.display()));
    }

    let (initial_path, initial_idx) = if let Some(arg) = arg_path {
        let explicit = Path::new(&arg);
        if explicit.is_file() {
            let idx = map_paths.iter().position(|p| p == explicit).unwrap_or(0);
            (explicit.to_path_buf(), idx)
        } else {
            let stem = arg.trim_end_matches(".map26");
            let idx = map_paths
                .iter()
                .position(|p| p.file_stem().and_then(|s| s.to_str()) == Some(stem))
                .ok_or_else(|| format!("map not found: {arg}"))?;
            (map_paths[idx].clone(), idx)
        }
    } else {
        (map_paths[0].clone(), 0)
    };

    let grid = grid::Grid::load(&initial_path)?;

    Ok(Inputs {
        grid,
        map_paths,
        initial_idx,
    })
}

#[must_use]
pub fn build(atlas: Arc<SpriteSet>, inputs: Inputs) -> app::App {
    app::App::new(atlas, inputs.grid, inputs.map_paths, inputs.initial_idx)
}
