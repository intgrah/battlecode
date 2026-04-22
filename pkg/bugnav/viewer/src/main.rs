use std::{env, path::Path, path::PathBuf, process};

use bugnav_viewer::{app, grid::Grid};
use eframe::egui;

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
        .flat_map(|it| it.flatten())
        .map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().and_then(|s| s.to_str()) == Some("map26"))
        .collect();
    out.sort();
    out
}

fn find_assets_dir(exe_dir: &Path) -> PathBuf {
    let candidates = [
        exe_dir.join("../../../bugnav/viewer/assets"),
        exe_dir.join("../../assets"),
        exe_dir.join("../assets"),
        Path::new("pkg/bugnav/viewer/assets").to_path_buf(),
        Path::new("assets").to_path_buf(),
    ];
    candidates
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| Path::new("assets").to_path_buf())
}

fn main() -> eframe::Result {
    let arg_path = env::args().nth(1);

    let maps_dir = find_maps_dir().unwrap_or_else(|| {
        eprintln!("cannot find maps/ directory from cwd or ancestors");
        process::exit(1);
    });
    let map_paths = collect_maps(&maps_dir);
    if map_paths.is_empty() {
        eprintln!("no .map26 files in {}", maps_dir.display());
        process::exit(1);
    }

    let (initial_path, initial_idx) = if let Some(arg) = arg_path {
        let explicit = Path::new(&arg);
        if explicit.is_file() {
            let idx = map_paths.iter().position(|p| p == explicit).unwrap_or(0);
            (explicit.to_path_buf(), idx)
        } else {
            let stem = arg.trim_end_matches(".map26");
            match map_paths
                .iter()
                .position(|p| p.file_stem().and_then(|s| s.to_str()) == Some(stem))
            {
                Some(i) => (map_paths[i].clone(), i),
                None => {
                    eprintln!("map not found: {arg}");
                    process::exit(1);
                }
            }
        }
    } else {
        (map_paths[0].clone(), 0)
    };

    let grid = Grid::load(&initial_path).unwrap_or_else(|e| {
        eprintln!("{e}");
        process::exit(1);
    });

    let exe = env::current_exe().unwrap_or_default();
    let exe_dir = exe.parent().unwrap_or_else(|| Path::new(".")).to_path_buf();
    let assets_dir = find_assets_dir(&exe_dir);

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 800.0])
            .with_title(format!("bugnav-viewer: {}", grid.name)),
        ..Default::default()
    };
    eframe::run_native(
        "bugnav-viewer",
        options,
        Box::new(move |cc| {
            Ok(Box::new(app::App::new(
                cc,
                grid,
                &assets_dir,
                map_paths,
                initial_idx,
            )))
        }),
    )
}
