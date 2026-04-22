pub use cambc_proto as proto;

mod app;
mod blueprint;
mod bp_io;
mod cost;
mod map;
mod map_view;
mod sequencing;
mod state;
mod symmetry;
mod ui;

use std::{env, path::Path, process};

use eframe::egui;

fn main() -> eframe::Result {
    let path = env::args().nth(1).unwrap_or_else(|| {
        eprintln!("usage: blueprint-editor <map.map26>");
        process::exit(1);
    });
    let map_path = Path::new(&path).canonicalize().unwrap_or_else(|e| {
        eprintln!("cannot resolve {path}: {e}");
        process::exit(1);
    });
    let map = map::load(&map_path).unwrap_or_else(|e| {
        eprintln!("{e}");
        process::exit(1);
    });

    let exe = env::current_exe().unwrap_or_default();
    let exe_dir = exe.parent().unwrap_or_else(|| Path::new("."));
    let candidates = [
        exe_dir.join("../../../blueprint/editor/assets"),
        exe_dir.join("../../assets"),
        exe_dir.join("../assets"),
        Path::new("pkg/blueprint/editor/assets").to_path_buf(),
        Path::new("assets").to_path_buf(),
    ];
    let assets_dir = candidates
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| Path::new("assets").to_path_buf());

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 800.0])
            .with_title(format!("blueprint-editor: {}", map.name)),
        ..Default::default()
    };
    eframe::run_native(
        "blueprint-editor",
        options,
        Box::new(move |cc| Ok(Box::new(app::App::new(cc, map, &assets_dir)))),
    )
}
